"""Tests del context server: ciclo de vida de tenants y persistencia del modelo."""

SAMPLE_MODEL = {
    "schemas": [
        {"title": "Building", "type": "object", "properties": {"id": {"type": "string"}}},
        {"title": "Device", "type": "object", "properties": {"id": {"type": "string"}}},
    ],
    "context": {"@context": {"Building": "https://example.org/Building"}},
    "descriptor": {"relationships": [{"sourceType": "Building", "property": "hasPart", "targetType": "Device"}]},
    "examples": {
        "Building": {"id": "urn:ngsi-ld:Building:001", "type": "Building"},
    },
    "packageName": "modelo.zip",
}


class TestTenantLifecycle:

    def test_list_empty(self, client):
        r = client.get("/tenants")
        assert r.status_code == 200
        assert r.json() == {"tenants": []}

    def test_create_and_list(self, client):
        r = client.post("/tenants", json={"name": "ibermot"})
        assert r.status_code == 200
        assert r.json()["created"] is True
        assert client.get("/tenants").json()["tenants"] == ["ibermot"]

    def test_create_is_idempotent(self, client):
        client.post("/tenants", json={"name": "ibermot"})
        r = client.post("/tenants", json={"name": "ibermot"})
        assert r.status_code == 200
        assert r.json()["created"] is False

    def test_invalid_tenant_name_rejected(self, client):
        for bad in ["../evil", "UPPER CASE", "", "a/b", ".."]:
            r = client.post("/tenants", json={"name": bad})
            assert r.status_code == 400, bad

    def test_delete_tenant(self, client):
        client.post("/tenants", json={"name": "ibermot"})
        r = client.delete("/tenants/ibermot")
        assert r.status_code == 200
        assert r.json()["removed"] is True
        assert client.get("/tenants").json()["tenants"] == []

    def test_delete_missing_tenant_is_ok(self, client):
        r = client.delete("/tenants/nadie")
        assert r.status_code == 200
        assert r.json()["removed"] is False


class TestModel:

    def test_get_model_of_missing_tenant_404(self, client):
        assert client.get("/tenants/nadie/model").status_code == 404

    def test_put_and_get_model(self, client):
        r = client.put("/tenants/ibermot/model", json=SAMPLE_MODEL)
        assert r.status_code == 200
        s = r.json()["summary"]
        assert s["schemas"] == 2
        assert s["context"] is True
        assert s["descriptor"] is True
        assert s["examples"] == 1

        m = client.get("/tenants/ibermot/model").json()
        assert len(m["schemas"]) == 2
        assert m["context"] == SAMPLE_MODEL["context"]
        assert m["descriptor"] == SAMPLE_MODEL["descriptor"]
        assert m["examples"]["Building"]["id"] == "urn:ngsi-ld:Building:001"
        assert m["packageName"] == "modelo.zip"
        assert m["updatedAt"]

    def test_put_replaces_previous_model(self, client):
        client.put("/tenants/ibermot/model", json=SAMPLE_MODEL)
        smaller = {"schemas": [{"title": "Person"}], "context": None, "descriptor": None, "examples": {}}
        client.put("/tenants/ibermot/model", json=smaller)
        m = client.get("/tenants/ibermot/model").json()
        assert len(m["schemas"]) == 1
        assert m["schemas"][0]["title"] == "Person"
        assert m["context"] is None
        assert m["examples"] == {}

    def test_url_load_clears_previous_context_on_disk(self, client):
        """Cada carga sustituye el tenant: URL externa → sin context/ en disco."""
        client.put("/tenants/ibermot/model", json=SAMPLE_MODEL)
        r = client.put(
            "/tenants/ibermot/model",
            json={
                "schemas": [{"title": "Person"}],
                "context": None,
                "descriptor": {"relationships": []},
                "examples": {},
                "contextUrl": "https://example.org/external-context.jsonld",
            },
        )
        assert r.status_code == 200
        assert r.json()["summary"]["context"] is False
        m = client.get("/tenants/ibermot/model").json()
        assert len(m["schemas"]) == 1
        assert m["context"] is None
        assert m["contextUrl"] == "https://example.org/external-context.jsonld"
        assert client.get("/tenants/ibermot/context.jsonld").status_code == 404

    def test_empty_tenant_returns_empty_model(self, client):
        client.post("/tenants", json={"name": "ibermot"})
        m = client.get("/tenants/ibermot/model").json()
        assert m["schemas"] == []
        assert m["context"] is None
        assert m["descriptor"] is None
        assert m["examples"] == {}

    def test_delete_model_keeps_tenant(self, client):
        client.put("/tenants/ibermot/model", json=SAMPLE_MODEL)
        r = client.delete("/tenants/ibermot/model")
        assert r.status_code == 200
        assert client.get("/tenants").json()["tenants"] == ["ibermot"]
        m = client.get("/tenants/ibermot/model").json()
        assert m["schemas"] == []

    def test_context_jsonld_endpoint(self, client):
        client.put("/tenants/ibermot/model", json=SAMPLE_MODEL)
        r = client.get("/tenants/ibermot/context.jsonld")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/ld+json")
        assert r.json() == SAMPLE_MODEL["context"]

    def test_context_jsonld_404_when_no_context(self, client):
        client.post("/tenants", json={"name": "ibermot"})
        assert client.get("/tenants/ibermot/context.jsonld").status_code == 404
