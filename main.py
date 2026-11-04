
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from aws_service import (
    get_ec2_instances,
    get_s3_buckets,
    get_monthly_service_costs,
    get_rds_instances,
    get_historical_monthly_costs,
    get_cost_insights,
    get_monthly_cost_comparison,
    get_cost_recommendations,
    get_ec2_cpu_metrics,
    get_rds_cpu_metrics,
    get_rds_connection_metrics,
    get_rds_storage_metrics,
    get_ebs_volumes,
    get_s3_storage_metrics,
    get_aws_budgets,
    get_budget_alerts
)

app = FastAPI(title="AWS Cloud Cost & Resource Monitor")

templates = Jinja2Templates(directory="template")


@app.get("/api/costs")
def monthly_costs():
    return get_monthly_service_costs()



@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )



@app.get("/health")
def health():
    return {"status": "healthy"}



@app.get("/api/rds")
def rds_resources():
    databases = get_rds_instances()

    return {
        "count": len(databases),
        "databases": databases
    }



@app.get("/api/costs/history")
def historical_costs():
    return get_historical_monthly_costs(month_count=6)




@app.get("/api/costs/insights")
def cost_insights():
    return get_cost_insights()

@app.get("/api/costs/comparison")
def monthly_cost_comparison():
    return get_monthly_cost_comparison()

@app.get("/api/costs/recommendations")
def cost_recommendations():
    return get_cost_recommendations()

@app.get("/api/budgets")
def aws_budgets():
    return get_aws_budgets()

@app.get("/api/ec2/{instance_id}/cpu")
def ec2_cpu_metrics(instance_id: str):
    return get_ec2_cpu_metrics(instance_id)

@app.get("/api/rds/{db_instance_id}/cpu")
def rds_cpu_metrics(db_instance_id: str):
    return get_rds_cpu_metrics(db_instance_id)


@app.get("/api/rds/{db_instance_id}/connections")
def rds_connection_metrics(db_instance_id: str):
    return get_rds_connection_metrics(db_instance_id)

@app.get("/api/rds/{db_instance_id}/storage")
def rds_storage_metrics(db_instance_id: str):
    return get_rds_storage_metrics(db_instance_id)

@app.get("/api/ebs")
def ebs_volumes():
    return get_ebs_volumes()


@app.get("/api/s3/{bucket_name}/storage")
def s3_storage_monitoring(bucket_name: str):
    try:
        metrics = get_s3_storage_metrics(bucket_name)

        return {
            "bucket_name": bucket_name,
            "datapoints": metrics
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    
@app.get("/api/budget-alerts")
def budget_alerts():
    return get_budget_alerts()


@app.get("/api/resources")
def all_resources():
    ec2 = get_ec2_instances()
    s3 = get_s3_buckets()
    rds = get_rds_instances()

    return {
        "region": "ap-south-1",
        "summary": {
            "ec2_instances": len(ec2),
            "s3_buckets": len(s3),
            "rds_instances": len(rds),
            "running_instances": sum(
                1 for item in ec2
                if item["state"] == "running"
            )
        },
        "ec2": ec2,
        "s3": s3,
        "rds": rds
    }





