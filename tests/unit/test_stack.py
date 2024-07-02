import aws_cdk as core
import aws_cdk.assertions as assertions

from user_service_aws.app import UserServiceAwsStack


def test_charts():
    app = core.App()
    stack = UserServiceAwsStack(app, "user-service-aws")
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties(
        "Custom::AWSCDK-EKS-HelmChart", {"Chart": "metrics-server"}
    )
    template.has_resource_properties(
        "Custom::AWSCDK-EKS-HelmChart", {"Chart": "cluster-autoscaler"}
    )
    template.has_resource_properties(
        "Custom::AWSCDK-EKS-HelmChart", {"Chart": "argo-cd"}
    )
    template.has_resource_properties(
        "Custom::AWSCDK-EKS-HelmChart", {"Chart": "aws-for-fluent-bit"}
    )
    template.has_resource_properties(
        "Custom::AWSCDK-EKS-HelmChart", {"Chart": "aws-cloudwatch-metrics"}
    )
