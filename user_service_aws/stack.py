from aws_cdk import CfnParameter, Stack, Tags, aws_ec2, aws_eks, aws_iam
from aws_cdk.lambda_layer_kubectl_v30 import KubectlV30Layer
from constructs import Construct

from .autoscaling import EksAutoScaling
from .cloudwatch import EksCloudWatch
from .service import UserService
from .storage import EksStorage


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

        EksStorage(self, "user-service-storage", cluster)
        EksAutoScaling(self, "user-service-autoscaling", cluster)
        EksCloudWatch(self, "user-service-cloudwatch", cluster)
        UserService(self, "user-service-argo", cluster)
