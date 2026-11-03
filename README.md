# Local Delivery Assignment System

An AWS-native delivery operations app deployed with Terraform and GitHub Actions.

## Architecture

- [AWS and DevOps architecture diagrams](.github/modernize/assessment/engines/facts/architecture-diagram.md)
- Amazon Cognito provides email sign-in and JWTs.
- Amazon API Gateway HTTP API protects the application routes with a Cognito JWT authorizer.
- AWS Lambda handles driver registration, delivery creation, driver assignment, delivery listing, and status changes.
- Amazon DynamoDB stores delivery jobs and drivers with on-demand billing and point-in-time recovery.
- Amazon S3 stores the static dispatch dashboard privately; a small Lambda serves those assets through the HTTPS API Gateway hostname.
- Amazon CloudWatch retains Lambda and API access logs.
- Terraform provisions the stack. GitHub Actions runs tests on pull requests and main-branch pushes; deployment is manual and gated by a GitHub environment.

## Local Validation

Use Python 3.13 and Terraform 1.10 or later.

```sh
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q
terraform fmt -check -recursive infrastructure
terraform -chdir=infrastructure init -backend=false
terraform -chdir=infrastructure validate
terraform -chdir=infrastructure/bootstrap init -backend=false
terraform -chdir=infrastructure/bootstrap validate
```

The tests use mocks and do not call AWS.

## AWS Bootstrap

Deployment creates billable AWS resources. Review the Terraform plan and expected service charges before applying. No AWS resources are created by local validation.

1. Choose an AWS account and region. Create a globally unique name for the Terraform state bucket and a globally unique Cognito base prefix (5-55 lowercase letters, digits, or hyphens). The deployment appends `-dev` or `-prod` so each environment gets its own Cognito domain.
2. With an authorized local AWS identity, provision the versioned, encrypted state bucket once:

	 ```sh
	 terraform -chdir=infrastructure/bootstrap init
	 terraform -chdir=infrastructure/bootstrap apply \
		 -var='state_bucket_name=REPLACE_WITH_UNIQUE_BUCKET_NAME' \
		 -var='aws_region=ap-southeast-1'
	 ```

3. Configure a GitHub Actions OIDC provider and a deployment role in IAM. Restrict its trust policy to this repository's `aws-deploy` environment and `sts.amazonaws.com` audience. Grant only the actions needed to apply this Terraform stack, access the state bucket, and pass the Lambda execution role. Do not store long-lived AWS access keys in GitHub.
4. In GitHub, create the `aws-deploy` environment and require an authorized reviewer. Add environment variable `AWS_REGION`, `TF_STATE_BUCKET`, and `COGNITO_DOMAIN_PREFIX`, plus secret `AWS_ROLE_TO_ASSUME` containing the IAM role ARN.
5. Run the `Validate and deploy` workflow manually from the `main` branch, choose `dev` or `prod`, and approve the protected environment deployment.
6. Open the `frontend_url` Terraform output and create a Cognito user through the hosted sign-in page. The first user can then register drivers and manage deliveries.

The Terraform backend uses S3 native state locking (`use_lockfile=true`), requiring Terraform 1.10 or later. Each environment uses a separate state key and Cognito domain. The base Cognito prefix must be globally unique. The `prod` workflow choice enables DynamoDB deletion protection; disable it only after deliberately reviewing a destruction plan.

This stack creates new environment-scoped DynamoDB tables; it does not import, alter, or migrate the existing `DeliveryJobs` and `DeliveryDrivers` tables used during local development. Existing records such as `JOB-73EFE5B4` remain in those original tables and will not appear in the deployed dashboard.

## Access Scope

This is a single-team demo: any signed-in Cognito user can read and modify every delivery and driver. Do not use it for multiple businesses or sensitive customer information until application-level roles, tenant isolation, and appropriate retention policies are added. AWS resources incur charges while deployed; run `terraform destroy` for an environment when it is no longer needed, after reviewing the data-retention impact.

## API Routes

All routes require a Cognito JWT in the `Authorization` header.

| Method | Route | Request |
| --- | --- | --- |
| `POST` | `/drivers` | `{"name":"Jordan Lee","phone":"+15551234567"}` |
| `POST` | `/deliveries` | `{"customer_name":"Jordan Lee","pickup_address":"Warehouse","delivery_address":"Market Street"}` |
| `POST` | `/deliveries/assign` | `{"job_id":"JOB-..."}` |
| `GET` | `/deliveries` | Optional `limit` and `last_evaluated_key` query parameters |
| `PATCH` | `/deliveries/status` | `{"job_id":"JOB-...","status":"PICKED_UP"}` |

Delivery progression is `PENDING` → `ASSIGNED` → `PICKED_UP` → `IN_TRANSIT` → `DELIVERED`. Completing a delivery releases its driver in the same DynamoDB transaction.