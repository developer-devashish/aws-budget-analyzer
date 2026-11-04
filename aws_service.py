
import os
import boto3
from dotenv import load_dotenv
from datetime import date, datetime, timedelta

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

session = boto3.Session(region_name=AWS_REGION)


def get_ec2_instances():
    ec2 = session.client("ec2")
    instances = []

    paginator = ec2.get_paginator("describe_instances")

    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                name = next(
                    (
                        tag["Value"]
                        for tag in instance.get("Tags", [])
                        if tag["Key"] == "Name"
                    ),
                    "Unnamed",
                )

                instances.append({
                    "id": instance["InstanceId"],
                    "name": name,
                    "type": instance["InstanceType"],
                    "state": instance["State"]["Name"],
                    "region": AWS_REGION,
                })

    return instances



def get_cost_recommendations():
    cost_data = get_monthly_service_costs()
    comparison = get_monthly_cost_comparison()

    services = cost_data.get("services", [])
    recommendations = []

    # 1. Identify highest-cost service
    if services:
        highest_service = max(
            services,
            key=lambda service: float(service["amount"])
        )

        recommendations.append({
            "category": "Highest Cost",
            "service": highest_service["service"],
            "message": (
                f"{highest_service['service']} is your "
                "highest-cost AWS service."
            ),
            "suggestion": (
                "Review its resource usage and check whether "
                "all resources are necessary."
            )
        })

    # 2. Check monthly spending trend
    percentage = comparison["percentage_change"]

    if percentage is not None and percentage > 20:
        recommendations.append({
            "category": "Cost Increase",
            "service": "AWS Overall",
            "message": (
                f"Your spending increased by {percentage}% "
                "compared with the previous month."
            ),
            "suggestion": (
                "Review your Cost Explorer report to identify "
                "which services caused the increase."
            )
        })

    elif percentage is not None and percentage < 0:
        recommendations.append({
            "category": "Cost Optimization",
            "service": "AWS Overall",
            "message": "Your AWS spending has decreased.",
            "suggestion": (
                "Continue monitoring your resource usage "
                "to maintain the savings."
            )
        })

    # 3. General recommendation
    recommendations.append({
        "category": "General",
        "service": "AWS Account",
        "message": "Review unused AWS resources regularly.",
        "suggestion": (
            "Check EC2 instances, unattached EBS volumes, "
            "unused RDS instances and unnecessary S3 storage."
        )
    })

    return {
        "total_recommendations": len(recommendations),
        "recommendations": recommendations
    }


def get_ec2_cpu_metrics(instance_id, hours=24):
    from datetime import datetime, timedelta, timezone

    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": instance_id
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=300,
        Statistics=["Average", "Maximum"]
    )

    datapoints = sorted(
        response.get("Datapoints", []),
        key=lambda item: item["Timestamp"]
    )

    return {
        "instance_id": instance_id,
        "average_cpu": (
            round(
                sum(point["Average"] for point in datapoints)
                / len(datapoints),
                2
            )
            if datapoints else None
        ),
        "maximum_cpu": (
            round(max(point["Maximum"] for point in datapoints), 2)
            if datapoints else None
        ),
        "unit": "Percent",
        "datapoints": [
            {
                "timestamp": point["Timestamp"].isoformat(),
                "average": round(point["Average"], 2),
                "maximum": round(point["Maximum"], 2)
            }
            for point in datapoints
        ]
    }





def get_s3_buckets():
    s3 = session.client("s3")
    response = s3.list_buckets()

    buckets = []

    for bucket in response.get("Buckets", []):
        name = bucket["Name"]

        location = s3.get_bucket_location(
            Bucket=name
        ).get("LocationConstraint")

        buckets.append({
            "name": name,
            "region": location or "us-east-1",
            "created": (
                bucket["CreationDate"].isoformat()
                if bucket.get("CreationDate")
                else None
            ),
        })

    return buckets

def get_monthly_service_costs():
    today = date.today()
    current_start = today.replace(day=1)

    # On the first day, show the previous month's costs.
    if today == current_start:
        if current_start.month == 1:
            start = date(current_start.year - 1, 12, 1)
        else:
            start = date(
                current_start.year,
                current_start.month - 1,
                1
            )

        end = current_start
        period_label = "previous_month"

    else:
        start = current_start
        end = today
        period_label = "current_month"

    client = boto3.client("ce", region_name="us-east-1")

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": end.isoformat()
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "SERVICE"
            }
        ]
    )

    costs = []

    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            amount = float(
                group["Metrics"]["UnblendedCost"]["Amount"]
            )

            costs.append({
                "service": group["Keys"][0],
                "amount": amount,
                "currency": group["Metrics"]["UnblendedCost"]["Unit"]
            })

    costs.sort(key=lambda item: item["amount"], reverse=True)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "period": period_label,
        "currency": "USD",
        "services": costs,
        "total": round(sum(item["amount"] for item in costs), 6)
    }


def get_rds_instances():
    rds = session.client("rds")
    databases = []

    paginator = rds.get_paginator("describe_db_instances")

    for page in paginator.paginate():
        for db in page.get("DBInstances", []):

            databases.append({
                "identifier": db.get("DBInstanceIdentifier"),
                "engine": db.get("Engine"),
                "engine_version": db.get("EngineVersion"),
                "instance_class": db.get("DBInstanceClass"),
                "status": db.get("DBInstanceStatus"),
                "storage_gb": db.get("AllocatedStorage"),
                "multi_az": db.get("MultiAZ"),
                "region": AWS_REGION,
            })

    return databases

def get_historical_monthly_costs(month_count=6):
    """
    Fetch total AWS costs for the last month_count months,
    ending with the previous completed month.
    """

    if not isinstance(month_count, int) or not 1 <= month_count <= 12:
        raise ValueError("month_count must be between 1 and 12")

    today = date.today()
    current_month = today.replace(day=1)

    # Calculate the first day of the month_count-month period.
    start_month = current_month.month - month_count
    start_year = current_month.year

    while start_month <= 0:
        start_month += 12
        start_year -= 1

    start_date = date(start_year, start_month, 1)

    # End date is the first day of the current month (exclusive).
    end_date = current_month

    client = boto3.client("ce", region_name="us-east-1")

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date.isoformat(),
            "End": end_date.isoformat()
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"]
    )

    monthly_costs = []

    for result in response.get("ResultsByTime", []):
        cost_data = result["Total"]["UnblendedCost"]

        monthly_costs.append({
            "month": date.fromisoformat(
                result["TimePeriod"]["Start"]
            ).strftime("%b %Y"),
            "amount": float(cost_data["Amount"]),
            "currency": cost_data["Unit"]
        })

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "currency": "USD",
        "monthly_costs": monthly_costs
    }


def get_cost_insights():
    cost_data = get_monthly_service_costs()

    services = cost_data.get("services", [])

    if not services:
        return {
            "highest_cost_service": None,
            "highest_cost": 0,
            "total_cost": 0
        }

    highest_service = max(
        services,
        key=lambda service: float(service["amount"])
    )

    return {
        "highest_cost_service": highest_service["service"],
        "highest_cost": highest_service["amount"],
        "total_cost": cost_data["total"]
    }


def get_monthly_cost_comparison():
    today = date.today()

    # First day of current month
    current_start = today.replace(day=1)

    # First day of previous month
    if current_start.month == 1:
        previous_start = date(current_start.year - 1, 12, 1)
    else:
        previous_start = date(
            current_start.year,
            current_start.month - 1,
            1
        )

    client = boto3.client("ce", region_name="us-east-1")

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": previous_start.isoformat(),
            "End": today.isoformat()
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"]
    )

    results = response.get("ResultsByTime", [])

    previous_cost = 0.0
    current_cost = 0.0

    for result in results:
        month_start = result["TimePeriod"]["Start"]

        amount = float(
            result["Total"]["UnblendedCost"]["Amount"]
        )

        if month_start == previous_start.isoformat():
            previous_cost = amount

        elif month_start == current_start.isoformat():
            current_cost = amount

    difference = current_cost - previous_cost

    if previous_cost > 0:
        percentage_change = (difference / previous_cost) * 100
    else:
        percentage_change = None

    return {
        "previous_month_cost": round(previous_cost, 4),
        "current_month_cost": round(current_cost, 4),
        "difference": round(difference, 4),
        "percentage_change": (
            round(percentage_change, 2)
            if percentage_change is not None else None
        ),
        "trend": (
            "increased" if difference > 0
            else "decreased" if difference < 0
            else "unchanged"
        )
    }


def get_rds_cpu_metrics(db_instance_id, days=1):
    from datetime import datetime, timedelta, timezone

    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="CPUUtilization",
        Dimensions=[
            {
                "Name": "DBInstanceIdentifier",
                "Value": db_instance_id
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Average", "Maximum"]
    )

    datapoints = sorted(
        response.get("Datapoints", []),
        key=lambda item: item["Timestamp"]
    )

    return {
        "db_instance_id": db_instance_id,
        "average_cpu": (
            round(
                sum(point["Average"] for point in datapoints)
                / len(datapoints), 2
            ) if datapoints else None
        ),
        "maximum_cpu": (
            round(max(point["Maximum"] for point in datapoints), 2)
            if datapoints else None
        ),
        "unit": "Percent",
        "datapoints": [
            {
                "timestamp": point["Timestamp"].isoformat(),
                "average": round(point["Average"], 2),
                "maximum": round(point["Maximum"], 2)
            }
            for point in datapoints
        ]
    }

def get_rds_connection_metrics(db_instance_id, days=1):
    from datetime import datetime, timedelta, timezone

    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="DatabaseConnections",
        Dimensions=[
            {
                "Name": "DBInstanceIdentifier",
                "Value": db_instance_id
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Average", "Maximum"]
    )

    datapoints = sorted(
        response.get("Datapoints", []),
        key=lambda item: item["Timestamp"]
    )

    return {
        "db_instance_id": db_instance_id,
        "average_connections": (
            round(sum(p["Average"] for p in datapoints) / len(datapoints), 2)
            if datapoints else None
        ),
        "maximum_connections": (
            round(max(p["Maximum"] for p in datapoints), 2)
            if datapoints else None
        ),
        "datapoints": [
            {
                "timestamp": p["Timestamp"].isoformat(),
                "average": round(p["Average"], 2),
                "maximum": round(p["Maximum"], 2)
            }
            for p in datapoints
        ]
    }

def get_rds_storage_metrics(db_instance_id, days=1):
    from datetime import datetime, timedelta, timezone

    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="FreeStorageSpace",
        Dimensions=[
            {
                "Name": "DBInstanceIdentifier",
                "Value": db_instance_id
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Average", "Minimum"]
    )

    datapoints = sorted(
        response.get("Datapoints", []),
        key=lambda item: item["Timestamp"]
    )

    return {
        "db_instance_id": db_instance_id,
        "average_free_storage_gb": (
            round(
                sum(p["Average"] for p in datapoints)
                / len(datapoints) / (1024 ** 3), 2
            ) if datapoints else None
        ),
        "minimum_free_storage_gb": (
            round(
                min(p["Minimum"] for p in datapoints)
                / (1024 ** 3), 2
            ) if datapoints else None
        ),
        "unit": "GB",
        "datapoints": [
            {
                "timestamp": p["Timestamp"].isoformat(),
                "average_gb": round(p["Average"] / (1024 ** 3), 2),
                "minimum_gb": round(p["Minimum"] / (1024 ** 3), 2)
            }
            for p in datapoints
        ]
    }

def get_ebs_volumes():
    ec2 = session.client("ec2")

    response = ec2.describe_volumes()
    volumes = []

    for volume in response.get("Volumes", []):
        attachments = volume.get("Attachments", [])

        volumes.append({
            "volume_id": volume["VolumeId"],
            "size_gb": volume["Size"],
            "volume_type": volume["VolumeType"],
            "state": volume["State"],
            "availability_zone": volume["AvailabilityZone"],
            "attached": len(attachments) > 0,
            "instance_id": (
                attachments[0]["InstanceId"]
                if attachments else None
            )
        })

    return {
        "total_volumes": len(volumes),
        "attached_volumes": sum(
            1 for volume in volumes if volume["attached"]
        ),
        "unattached_volumes": sum(
            1 for volume in volumes if not volume["attached"]
        ),
        "volumes": volumes
    }



def get_s3_storage_metrics(bucket_name):
    cloudwatch = session.client("cloudwatch")

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/S3",
        MetricName="BucketSizeBytes",
        Dimensions=[
            {"Name": "BucketName", "Value": bucket_name},
            {"Name": "StorageType", "Value": "StandardStorage"}
        ],
        StartTime=datetime.utcnow() - timedelta(days=7),
        EndTime=datetime.utcnow(),
        Period=86400,
        Statistics=["Average"]
    )

    datapoints = sorted(
        response["Datapoints"],
        key=lambda x: x["Timestamp"]
    )

    return [
        {
            "timestamp": point["Timestamp"].isoformat(),
            "storage_gb": round(point["Average"] / (1024 ** 3), 3)
        }
        for point in datapoints
    ]

def get_aws_budgets():
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]

    budgets = session.client("budgets", region_name="us-east-1")

    response = budgets.describe_budgets(
        AccountId=account_id
    )

    budget_list = []

    for budget in response.get("Budgets", []):
        calculated = budget.get("CalculatedSpend", {})

        budget_list.append({
            "name": budget.get("BudgetName"),
            "limit": float(
                budget.get("BudgetLimit", {}).get("Amount", 0)
            ),
            "actual_spend": float(
                calculated.get("ActualSpend", {}).get("Amount", 0)
            ),
            "forecasted_spend": float(
                calculated.get("ForecastedSpend", {}).get("Amount", 0)
            ),
            "currency": budget.get("BudgetLimit", {}).get("Unit"),
            "time_unit": budget.get("TimeUnit")
        })

    return {
        "total_budgets": len(budget_list),
        "budgets": budget_list
    }

def get_budget_alerts():
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]

    budgets_client = session.client(
        "budgets",
        region_name="us-east-1"
    )

    response = budgets_client.describe_budgets(
        AccountId=account_id
    )

    alerts = []

    for budget in response.get("Budgets", []):
        budget_name = budget["BudgetName"]

        notifications = budgets_client.describe_notifications_for_budget(
            AccountId=account_id,
            BudgetName=budget_name
        )

        for notification in notifications.get("Notifications", []):
            alerts.append({
                "budget_name": budget_name,
                "notification_type": notification.get("NotificationType"),
                "comparison_operator": notification.get("ComparisonOperator"),
                "threshold": notification.get("Threshold"),
                "threshold_type": notification.get("ThresholdType"),
                "notification_state": notification.get("NotificationState")
            })

    return {
        "total_alerts": len(alerts),
        "alerts": alerts
    }


if __name__ == "__main__":
    try:
        print("\n===== EC2 INSTANCES =====")
        for instance in get_ec2_instances():
            print(instance)

        print("\n===== S3 BUCKETS =====")
        for bucket in get_s3_buckets():
            print(bucket)

        print("\n===== RDS DATABASES =====")
        for database in get_rds_instances():
            print(database)

    except Exception as error:
        print("AWS resource retrieval failed:", error)
