from aws_cdk import Stack, aws_eks, aws_iam
from constructs import Construct


class EksCloudWatch(Construct):

    def __init__(
        self,
        scope: Stack,
        construct_id: str,
        cluster: aws_eks.Cluster,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        chart = cluster.add_helm_chart(
            "AwsForFluentBit",
            chart="aws-for-fluent-bit",
            release="aws-for-fluent-bit",
            repository="https://aws.github.io/eks-charts",
            values={
                "cloudWatch": {
                    "enabled": True,
                    "region": scope.region,
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
        )
        chart.node.add_dependency(service_account)
