from fastapi import APIRouter, HTTPException
from kink import inject
from services.serv_bsv import BsvService
from pydantic import BaseModel


class URLDto(BaseModel):
    url: str


class VCSLDto(BaseModel):
    id: str
    ipns: str


@inject
class VcslRouter:
    def __init__(self, bsv_service: BsvService):
        self.bsv_service: BsvService = bsv_service
        self.router = APIRouter()
        self.router.add_api_route("/vcsl/issuer/{issuer_id}", self.set_issuer_url, methods=["POST"])
        self.router.add_api_route("/vcsl/issuer/{issuer_id}", self.get_issuer_url, methods=["GET"])
        self.router.add_api_route("/vcsl", self.add_vcsl, methods=["POST"])
        self.router.add_api_route("/vcsl/{id}", self.get_vcsl, methods=["GET"])

    async def set_issuer_url(self, issuer_id: str, url_data: URLDto):
        if url_data is None or url_data.url is None:
            raise HTTPException(status_code=400, detail="URL data not provided")
        try:
            txid = self.bsv_service.set_issuer_url(issuer_id=issuer_id, new_issuer_url=url_data.url)
            if txid:
                return {"issuer_id": issuer_id, "txid": txid}
            else:
                return {"issuer_id": issuer_id, "status": "URL updated off-chain, anchoring failed or skipped"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error setting issuer URL: {e}")

    async def add_vcsl(self, data: VCSLDto):
        if data is None or data.id is None or data.ipns is None:
            raise HTTPException(status_code=400, detail="VCSL data not provided")
        try:
            txid = self.bsv_service.add_vcsl(id=data.id, ipns=data.ipns)
            return {"id": data.id, "txid": txid}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error adding vcsl: {e}")

    async def get_issuer_url(self, issuer_id: str):
        try:
            url = self.bsv_service.get_issuer_url(issuer_id=issuer_id)
            if url is None:
                raise HTTPException(status_code=404, detail=f"Issuer URL not found for {issuer_id}")
            return {"issuer_id": issuer_id, "url": url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error retrieving issuer URL: {e}")

    async def get_vcsl(self, id: str):
        try:
            ipns, txid = self.bsv_service.get_vcsl(id=id)
            if ipns is None:
                raise HTTPException(status_code=404, detail=f"VCSL data not found for id {id}")
            return {"id": id, "ipns": ipns, "txid": txid}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error retrieving VCSL data: {e}")
