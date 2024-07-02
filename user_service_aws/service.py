import importlib.resources
import yaml
from aws_cdk import Stack, aws_eks
from constructs import Construct


def load(filename):
    with (
        importlib.resources.files("user_service_aws")
        .joinpath(filename)
        .open("r") as stream
    ):
        return yaml.safe_load(stream)


class UserService(Construct):

    def __init__(
        self,
        scope: Stack,
        construct_id: str,
        cluster: aws_eks.Cluster,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
