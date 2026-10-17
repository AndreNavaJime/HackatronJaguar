"""API tests for CPU-only exploratory flank matcher (no jaguar identity assertion)."""
import io
import json
import random

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app

client=TestClient(app)


def feature_photo(seed=4):
    rnd=random.Random(seed)
    im=Image.new("RGB",(320,240),"#d7b682")
    draw=ImageDraw.Draw(im)
    for _ in range(140):
        x=rnd.randrange(12,308)
        y=rnd.randrange(12,228)
        radius=rnd.randrange(2,7)
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),outline="#2d231a",width=2)
    output=io.BytesIO()
    im.save(output,format="PNG")
    return output.getvalue()


def request(query=None,refs=None,labels=None,flanks=None,side="left"):
    query=query or feature_photo()
    refs=refs or [feature_photo()]
    labels=labels if labels is not None else ["JAG-001"]
    flanks=flanks if flanks is not None else ["left"]
    files=[("query",("query.png",query,"image/png"))]
    files.extend(("references",(f"ref-{i}.png",data,"image/png")) for i,data in enumerate(refs))
    return client.post("/api/individuals/compare",files=files,
      data={"labels":json.dumps(labels),"flanks":json.dumps(flanks),"query_flank":side})


def test_identical_flank_has_geometrically_coherent_features():
    result=request()
    assert result.status_code==200,result.text
    data=result.json()
    assert data["engine"]=="opencv_local_features_v1"
    assert data["identity_verified"] is False
    assert data["hotspotter_installed"] is False
    assert data["candidates"][0]["label"]=="JAG-001"
    assert data["candidates"][0]["coherent_matches"]>=7
    assert data["candidates"][0]["status"]=="candidate_for_review"
    assert data["candidates"][0]["evidence_image"].startswith("data:image/jpeg;base64,")


def test_opposite_flanks_not_compared():
    response=request(flanks=["right"])
    assert response.status_code==200
    candidate=response.json()["candidates"][0]
    assert candidate["status"]=="incompatible_flank"
    assert candidate["coherent_matches"]==0


def test_uninformative_photo_not_claimed_identical():
    img=Image.new("RGB",(320,240),"#cdb684")
    out=io.BytesIO();img.save(out,format="PNG")
    response=request(query=out.getvalue())
    assert response.status_code==200
    assert response.json()["candidates"][0]["status"]=="insufficient_evidence"


def test_bad_metadata_and_oversized_image_rejected():
    assert request(labels=[""]).status_code==422
    assert request(flanks=["sideways"]).status_code==422
    assert request(refs=[feature_photo()]*7,labels=["JAG"]*7,
       flanks=["left"]*7).status_code==422
    assert request(query=b"a"*(8*1024*1024+1)).status_code==413
