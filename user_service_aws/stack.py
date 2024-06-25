import importlib.resources
import os

import yaml
from aws_cdk import CfnParameter, Stack, aws_ec2, aws_eks, aws_iam
from aws_cdk.lambda_layer_kubectl_v29 import KubectlV29Layer
from constructs import Construct


class UserServiceAwsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        admin = aws_iam.ArnPrincipal(
            CfnParameter(
                self,
                "AdminArn",
                type="String",
                description="ARN of the admin user",
            ).value_as_string
        )

        cluster = aws_eks.Cluster(
            self,
            "user-service",
            cluster_name="user-service",
            version=aws_eks.KubernetesVersion.V1_30,
            kubectl_layer=KubectlV29Layer(self, "user-service-layer"),
            default_capacity=0,
            masters_role=aws_iam.Role(
                self,
                "user-service-role",
                assumed_by=admin,  # type: ignore
            ),  # type: ignore
            authentication_mode=aws_eks.AuthenticationMode.API_AND_CONFIG_MAP,
            vpc=aws_ec2.Vpc(self, "user-service-vpc", max_azs=2),
            vpc_subnets=[
                {"subnetType": aws_ec2.SubnetType.PRIVATE_WITH_EGRESS}
            ],
        )

        # The API shokes on the ARN and I cannot find how to provide it.
        # cluster.grant_access(
        #     "user-service-admin-access",
        #     principal=admin.arn,
        #     access_policies=[
        #         aws_eks.AccessPolicy.from_access_policy_name(
        #             "AmazonEKSAdminViewPolicy",
        #             access_scope_type=aws_eks.AccessScopeType.CLUSTER,
        #         )
        #     ],
        # )

        cluster.add_nodegroup_capacity(
            "user-service-capacity",
            min_size=2,
            max_size=4,
            instance_types=[aws_ec2.InstanceType("t3.medium")],
            capacity_type=aws_eks.CapacityType.SPOT,
            ami_type=aws_eks.NodegroupAmiType.AL2023_X86_64_STANDARD,
        )

        self.configure_autoscaling(cluster)
        self.configure_cloudwatch(cluster)

        argo_cd = cluster.add_helm_chart(
            "argo-cd",
            chart="argo-cd",
            release="argo-cd",
            repository="https://argoproj.github.io/argo-helm",
            version="7.2.1",
            namespace="argocd",
        )
        # We can do more fancy things, but we just add the application
        with (
            importlib.resources.files("user_service_aws")
            .joinpath("userservice.yaml")
            .open("r") as stream
        ):
            cluster.add_manifest(
                "user-service-application", yaml.safe_load(stream)
            ).node.add_dependency(argo_cd)

    def configure_autoscaling(self, cluster: aws_eks.Cluster):
        service_account = cluster.add_service_account(
            "user-service-autoscaler",
            name="user-service-autoscaler",
            namespace="kube-system",
        )

        service_account.add_to_principal_policy(
            aws_iam.PolicyStatement(
                resources=["*"],
                actions=[
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeAutoScalingInstances",
                    "autoscaling:DescribeLaunchConfigurations",
                    "autoscaling:DescribeScalingActivities",
                    "autoscaling:DescribeTags",
                    "ec2:DescribeImages",
                    "ec2:DescribeInstanceTypes",
                    "ec2:DescribeLaunchTemplateVersions",
                    "ec2:GetInstanceTypesFromInstanceRequirements",
                    "eks:DescribeNodegroup",
                    "autoscaling:SetDesiredCapacity",
                    "autoscaling:TerminateInstanceInAutoScalingGroup",
                ],
            )
        )

        cluster.add_helm_chart(
            "ClusterAutoscaler",
            chart="cluster-autoscaler",
            release="cluster-autoscaler",
            repository="https://kubernetes.github.io/autoscaler",
            values={
                "rbac": {
                    "serviceAccount": {
                        "create": False,
                        "name": "user-service-autoscaler",
                    },
                },
                "awsRegion": os.getenv("CDK_DEFAULT_REGION"),
                "autoDiscovery": {
                    "clusterName": cluster.cluster_name,
                },
            },
            version="9.37.0",
            namespace="kube-system",
        ).node.add_dependency(service_account)

        cluster.add_helm_chart(
            "MetricsServer",
            chart="metrics-server",
            release="metrics-server",
            repository="https://charts.bitnami.com/bitnami",
            namespace="kube-system",
        ).node.add_dependency(service_account)

    def configure_cloudwatch(self, cluster: aws_eks.Cluster):
        service_account = cluster.add_service_account(
            "aws-cloudwatch",
            name="aws-cloudwatch",
            namespace="kube-system",
        )

        service_account.role.add_managed_policy(
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchAgentServerPolicy"
            )
        )

        cluster.add_helm_chart(
            "AwsCloudWatchMetrics",
            chart="aws-cloudwatch-metrics",
            release="aws-cloudwatch-metrics",
            repository="https://aws.github.io/eks-charts",
            values={
                "clusterName": cluster.cluster_name,
                "serviceAccount": {
                    "create": False,
                    "name": "aws-cloudwatch",
                },
            },
            namespace="kube-system",
        ).node.add_dependency(service_account)

        cluster.add_helm_chart(
            "AwsForFluentBit",
            chart="aws-for-fluent-bit",
            release="aws-for-fluent-bit",
            repository="https://aws.github.io/eks-charts",
            values={
                "cloudWatch": {
                    "enabled": True,
                    "region": self.region,
                    "logGroupName": "/aws/containerinsights/"
                    f"${cluster.cluster_name}/application",
                    "logStreamPrefix": "${HOST_NAME}-",
                },
                "serviceAccount": {
                    "create": False,
                    "name": "aws-cloudwatch",
                },
            },
            namespace="kube-system",
        ).node.add_dependency(service_account)
