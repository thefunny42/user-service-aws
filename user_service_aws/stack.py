import importlib.resources
import os

import yaml
from aws_cdk import CfnParameter, Stack, Tags, aws_ec2, aws_eks, aws_iam
from aws_cdk.lambda_layer_kubectl_v30 import KubectlV30Layer
from constructs import Construct


def load(filename):
    with (
        importlib.resources.files("user_service_aws")
        .joinpath(filename)
        .open("r") as stream
    ):
        return yaml.safe_load(stream)


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

        vpc = aws_ec2.Vpc(self, "user-service-vpc", max_azs=2)
        for subnet in vpc.select_subnets(
            subnet_type=aws_ec2.SubnetType.PUBLIC
        ).subnets:
            Tags.of(subnet).add("kubernetes.io/role/elb", "1")
        for subnet in vpc.select_subnets(
            subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS
        ).subnets:
            Tags.of(subnet).add("kubernetes.io/role/internal-elb", "1")

        cluster = aws_eks.Cluster(
            self,
            "user-service",
            cluster_name="user-service",
            version=aws_eks.KubernetesVersion.V1_30,
            kubectl_layer=KubectlV30Layer(self, "user-service-layer"),
            default_capacity=0,
            masters_role=aws_iam.Role(
                self,
                "user-service-role",
                assumed_by=admin,  # type: ignore
            ),  # type: ignore
            authentication_mode=aws_eks.AuthenticationMode.API_AND_CONFIG_MAP,
            vpc=vpc,
            vpc_subnets=[
                {"subnetType": aws_ec2.SubnetType.PRIVATE_WITH_EGRESS}
            ],
        )

        # The API shokes on the ARN from organizations (I think)
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

        self.configure_storage(cluster)
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

        manifest = cluster.add_manifest(
            "user-service-application", load("userservice.yaml")
        )
        manifest.node.add_dependency(argo_cd)

    def configure_storage(self, cluster: aws_eks.Cluster):
        # The name of the service account is important
        service_account = cluster.add_service_account(
            "user-service-ebs",
            name="ebs-csi-controller-sa",
            namespace="kube-system",
        )

        service_account.role.add_managed_policy(
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonEBSCSIDriverPolicy"
            )
        )

        addon = aws_eks.CfnAddon(
            self,
            "user-service-ebs-driver",
            addon_name="aws-ebs-csi-driver",
            cluster_name=cluster.cluster_name,
            resolve_conflicts="OVERWRITE",
            addon_version="v1.32.0-eksbuild.1",
            service_account_role_arn=service_account.role.role_arn,
        )
        addon.node.add_dependency(service_account)

        manifest = cluster.add_manifest(
            "user-service-ebs-storage-class",
            {
                "apiVersion": "storage.k8s.io/v1",
                "kind": "StorageClass",
                "metadata": {
                    "name": "ebs-sc",
                    "annotations": {
                        "storageclass.kubernetes.io/is-default-class": "true"
                    },
                },
                "provisioner": "ebs.csi.aws.com",
                "volumeBindingMode": "WaitForFirstConsumer",
                "parameters": {"type": "gp3"},
            },
        )
        manifest.node.add_dependency(addon)

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

        chart = cluster.add_helm_chart(
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
            namespace="kube-system",
        )
        chart.node.add_dependency(service_account)

        chart = cluster.add_helm_chart(
            "MetricsServer",
            chart="metrics-server",
            release="metrics-server",
            repository="https://charts.bitnami.com/bitnami",
            namespace="kube-system",
        )
        chart.node.add_dependency(service_account)

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

        chart = cluster.add_helm_chart(
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
        )
        chart.node.add_dependency(service_account)

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
