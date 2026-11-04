
import boto3
from datetime import date, timedelta
from botocore.exceptions import ClientError

# Cost Explorer API uses the us-east-1 endpoint.
client = boto3.client("ce", region_name="us-east-1")

today = date.today()
start = today.replace(day=1)
end = today + timedelta(days=1)  # End date is exclusive

try:
    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": end.isoformat(),
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )

    for period in response["ResultsByTime"]:
        amount = period["Total"]["UnblendedCost"]

        print("Period:", period["TimePeriod"])
        print("Amount:", amount["Amount"])
        print("Currency:", amount["Unit"])

    if response.get("NextPageToken"):
        print(
            "More results are available. "
            "No additional request was made."
        )

except ClientError as error:
    print("AWS Cost Explorer request failed:")
    print(error.response["Error"]["Code"])
    print(error.response["Error"]["Message"])
