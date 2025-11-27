from fastapi import FastAPI, Query, HTTPException, status,Depends,Request
from typing import Optional
import requests, os
import redis
from dotenv import load_dotenv
from json import JSONDecodeError
import requests.exceptions
import json
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

app = FastAPI()

load_dotenv()

HOST = os.getenv("HOST", "missing")
PORT = int(os.getenv("PORT", "missing"))
api_key = os.getenv("APIKEY", "missing")
r = redis.Redis(host=HOST, port=PORT, decode_responses=True)

@app.on_event("startup")
async def startup():
    await FastAPILimiter.init(r)

async def get_client_ip(request: Request):
    return request.client.host


@app.get("/{place}", dependencies=[Depends(RateLimiter(times=5, seconds=60))])
def get_weather(
    place: str,
    to: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
):

    base_url = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Weather API key is not configured.",
        )

    if from_ and to:
        url = f"{base_url}{place}/{from_}/{to}?unitGroup=us&include=days&key={api_key}&contentType=json"
    else:
        url = f"{base_url}{place}/today?unitGroup=us&include=days&key={api_key}&contentType=json"

    cached = r.get(url)
    if cached:
        return json.loads(cached)

    try:
        weather = requests.get(url, timeout=2)
        weather.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "Weather API request timed out."
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to Weather API server.",
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Weather API request failed")

    if weather.status_code == status.HTTP_200_OK:
        r.set(url, json.dumps(weather.json()), ex=3600)
    
    try:
        return weather.json()
    except JSONDecodeError:
        return weather.text
