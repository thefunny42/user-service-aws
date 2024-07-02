from aws_cdk import Stack, aws_eks, aws_iam
from constructs import Construct


class EksStorage(Construct):

    def __init__(
        self,
        scope: Stack,
        construct_id: str,
        cluster: aws_eks.Cluster,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The name of the service account is fixed and important.
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
