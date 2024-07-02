import os

import aws_cdk as cdk

from .stack import UserServiceAwsStack


def app():  # pragma: no cover
    app = cdk.App()
    UserServiceAwsStack(
        app,
        "UserServiceAwsStack",
        env=cdk.Environment(
            account=os.getenv("CDK_DEFAULT_ACCOUNT"),
            region=os.getenv("CDK_DEFAULT_REGION"),
        ),
    )

    app.synth()
