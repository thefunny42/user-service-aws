from aws_cdk import Stack, aws_eks, aws_iam
from constructs import Construct


class EksAutoScaling(Construct):

    def __init__(
        self,
        scope: Stack,
        construct_id: str,
        cluster: aws_eks.Cluster,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
                "awsRegion": scope.region,
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
