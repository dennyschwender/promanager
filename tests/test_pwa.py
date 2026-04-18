"""Tests for PWA endpoints: service worker, manifest."""

import pytest
from app.config import settings


def test_sw_js_served(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert resp.headers.get("service-worker-allowed") == "/"
    assert "addEventListener" in resp.text


def test_manifest_json(client):
    resp = client.get("/manifest.json")
    assert resp.status_code == 200
    assert "manifest" in resp.headers["content-type"] or "json" in resp.headers["content-type"]
    data = resp.json()
    assert data["name"] == settings.APP_NAME
    assert data["short_name"] == settings.APP_NAME
    assert data["display"] == "standalone"
    assert data["start_url"] == "/dashboard"
    assert len(data["icons"]) == 2
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes


def test_favicon_ico(client):
    resp = client.get("/static/img/favicon.ico")
    assert resp.status_code == 200


def test_icon_192(client):
    resp = client.get("/static/img/icon-192.png")
    assert resp.status_code == 200


def test_icon_512(client):
    resp = client.get("/static/img/icon-512.png")
    assert resp.status_code == 200
