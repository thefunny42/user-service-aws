# Deploy user service on Amazon with CDK

This creates an EKS cluster on amazon, install ArgoCD and hooks up the user
service application there.

This will cost about 2 dollars for a few hours of testing.

This is built with hatch, so you need to have hatch installed (for instance
via pipx), and you need to have the Amazon CDK installed. You can do that with
the help of nave to have the latest version of node.js.

To setup the environment:

```shell
    export ADMIN_ARN=$(aws sts get-caller-identity --query Arn --output text  | grep '^arn:')
    export REGION=$(aws configure get region)
    nave use latest
    npm install -g aws-cdk
    cdk bootstrap
    cdk deploy --parameters AdminArn=$ADMIN_ARN
```

The deploy step can take a bit of time the first time (about 16 minutes). Follow
the instructions in the output to configure kubectl.

You can validate the result by looking at the resources and check that they
all come online:

```shell
    kubectl get all -A
```

After a few minutes ArgoCD will pull the application and put in place.

## Access ArgoCD

You can in a terminal:

```shell
     kubectl port-forward svc/argo-cd-argocd-server -n argocd 8080:443
```

And in a different one:

```shell
    argocd admin initial-password -n argocd
```

And open a browser at http://localhost:8080


## Cleanup

You can tear down everthing with:

```shell
    nave use latest
    cdk destroy
```

You can cleanup the bootstrap stack in CloudFormation too, and some CloudWatch
logs.