"""
Tests de integración para los endpoints de construcción de grafos.

  POST /api/graph/orion/build      — grafo de instancias Orion-LD
  POST /api/graph/schema/build     — grafo abstracto del modelo
  POST /api/graph/schema/type-view — detalle de un tipo del schema

No requieren Orion-LD real; trabajan con datos de entrada directos.
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Fixtures de datos reutilizables
# ══════════════════════════════════════════════════════════════════════════════

ENTITIES_SIMPLE = [
    {"id": "urn:ngsi-ld:Machine:001", "type": "Machine"},
    {"id": "urn:ngsi-ld:Area:001",    "type": "Area"},
]

ENTITIES_WITH_RELATIONSHIP = [
    {
        "id": "urn:ngsi-ld:Machine:001",
        "type": "Machine",
        "locatedIn": {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"},
    },
    {"id": "urn:ngsi-ld:Area:001", "type": "Area"},
]

ENTITIES_WITH_IMPLICIT_LINK = [
    {
        "id": "urn:ngsi-ld:Machine:001",
        "type": "Machine",
        # Property cuyo value es un URN → enlace implícito
        "operator": {"type": "Property", "value": "urn:ngsi-ld:Person:001"},
    },
]

RELATIONSHIPS = [
    {"from": "Machine", "to": "Area", "property": "https://example.org/locatedIn", "implicit": False},
]

TYPES = ["Machine", "Area", "Plant"]

RELATIONSHIPS_FULL = [
    {"from": "Machine", "to": "Area",    "property": "https://example.org/locatedIn", "implicit": False},
    {"from": "Plant",   "to": "Machine", "property": "https://example.org/hasMachine", "implicit": False},
]


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/graph/orion/build
# ══════════════════════════════════════════════════════════════════════════════

class TestOrionGraphBuild:

    def test_returns_200_with_ok_true(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_SIMPLE,
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_response_has_nodes_and_links_lists(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_SIMPLE,
        })
        data = r.json()
        assert isinstance(data.get("nodes"), list)
        assert isinstance(data.get("links"), list)

    def test_node_count_matches_input_entities(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_SIMPLE,
        })
        assert len(r.json()["nodes"]) == 2

    def test_explicit_relationship_creates_link(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_WITH_RELATIONSHIP,
            "relationships": RELATIONSHIPS,
        })
        data = r.json()
        assert len(data["links"]) == 1
        assert data["links"][0]["implicit"] is False

    def test_implicit_link_from_property_with_urn_value(self, client):
        """Property.value que es un URN crea un enlace implícito."""
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_WITH_IMPLICIT_LINK,
        })
        data = r.json()
        links = data["links"]
        assert len(links) == 1
        assert links[0]["implicit"] is True

    def test_implicit_flag_false_when_property_in_descriptor(self, client):
        """Si la propiedad está en el descriptor, el enlace NO es implícito."""
        entities = [
            {
                "id": "urn:ngsi-ld:Machine:001",
                "type": "Machine",
                "operator": {"type": "Property", "value": "urn:ngsi-ld:Person:001"},
            },
        ]
        relationships = [
            {"from": "Machine", "to": "Person", "property": "https://example.org/operator", "implicit": False},
        ]
        r = client.post("/api/graph/orion/build", json={
            "entities": entities,
            "relationships": relationships,
        })
        data = r.json()
        assert len(data["links"]) == 1
        assert data["links"][0]["implicit"] is False

    def test_unknown_relationship_target_added_as_ghost_node(self, client):
        """Si el target de un Relationship no existe como entidad, se añade como nodo fantasma."""
        entities = [
            {
                "id": "urn:ngsi-ld:Machine:001",
                "type": "Machine",
                "locatedIn": {"type": "Relationship", "object": "urn:ngsi-ld:Area:999"},
            },
        ]
        r = client.post("/api/graph/orion/build", json={"entities": entities})
        data = r.json()
        node_ids = [n["id"] for n in data["nodes"]]
        assert "urn:ngsi-ld:Area:999" in node_ids

    def test_empty_entities_returns_empty_graph(self, client):
        r = client.post("/api/graph/orion/build", json={"entities": []})
        data = r.json()
        assert data.get("ok") is True
        assert data["nodes"] == []
        assert data["links"] == []

    def test_entity_without_id_is_ignored(self, client):
        """Entidades sin campo 'id' se ignoran en la construcción del grafo."""
        entities = [
            {"type": "Machine"},  # sin id
            {"id": "urn:ngsi-ld:Area:001", "type": "Area"},
        ]
        r = client.post("/api/graph/orion/build", json={"entities": entities})
        data = r.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "urn:ngsi-ld:Area:001"

    def test_stats_field_reflects_input(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_SIMPLE,
        })
        stats = r.json().get("stats", {})
        assert stats.get("input_entities") == 2

    def test_node_has_id_type_and_label(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": [{"id": "urn:ngsi-ld:Machine:001", "type": "Machine"}],
        })
        node = r.json()["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "label" in node

    def test_node_label_uses_full_id_tail_without_truncating(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": [{"id": "urn:ngsi-ld:Robot:robot-pintura-004", "type": "Robot"}],
        })
        node = r.json()["nodes"][0]
        assert node["label"] == "robot-pintura-004"

    def test_link_has_source_target_property_implicit(self, client):
        r = client.post("/api/graph/orion/build", json={
            "entities": ENTITIES_WITH_RELATIONSHIP,
            "relationships": RELATIONSHIPS,
        })
        link = r.json()["links"][0]
        assert "source" in link
        assert "target" in link
        assert "property" in link
        assert "implicit" in link

    def test_missing_entities_field_returns_422(self, client):
        r = client.post("/api/graph/orion/build", json={})
        assert r.status_code == 422

    def test_multiple_entities_and_links(self, client):
        entities = [
            {
                "id": "urn:ngsi-ld:Plant:001",
                "type": "Plant",
                "hasMachine": {"type": "Relationship", "object": "urn:ngsi-ld:Machine:001"},
            },
            {
                "id": "urn:ngsi-ld:Machine:001",
                "type": "Machine",
                "locatedIn": {"type": "Relationship", "object": "urn:ngsi-ld:Area:001"},
            },
            {"id": "urn:ngsi-ld:Area:001", "type": "Area"},
        ]
        r = client.post("/api/graph/orion/build", json={
            "entities": entities,
            "relationships": RELATIONSHIPS_FULL,
        })
        data = r.json()
        assert len(data["nodes"]) == 3
        assert len(data["links"]) == 2


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/graph/schema/build
# ══════════════════════════════════════════════════════════════════════════════

class TestSchemaGraphBuild:

    def test_returns_ok_with_nodes_and_links(self, client):
        r = client.post("/api/graph/schema/build", json={
            "types": TYPES,
            "relationships": RELATIONSHIPS_FULL,
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data["nodes"], list)
        assert isinstance(data["links"], list)

    def test_node_count_matches_types(self, client):
        r = client.post("/api/graph/schema/build", json={"types": TYPES})
        assert len(r.json()["nodes"]) == len(TYPES)

    def test_links_only_between_known_types(self, client):
        """Relaciones cuyo from o to no está en types se descartan."""
        r = client.post("/api/graph/schema/build", json={
            "types": ["Machine", "Area"],
            "relationships": [
                {"from": "Machine",  "to": "Area",    "property": "locatedIn",  "implicit": False},
                {"from": "Unknown",  "to": "Area",    "property": "ignored",    "implicit": False},
                {"from": "Machine",  "to": "Missing", "property": "also-gone",  "implicit": False},
            ],
        })
        data = r.json()
        assert len(data["links"]) == 1
        assert data["links"][0]["property"] == "locatedIn"

    def test_metrics_include_degree_info(self, client):
        r = client.post("/api/graph/schema/build", json={
            "types": ["Machine", "Area"],
            "relationships": [
                {"from": "Machine", "to": "Area", "property": "locatedIn", "implicit": False},
            ],
        })
        metrics = r.json().get("metrics", {})
        assert "out_degree" in metrics
        assert "in_degree" in metrics
        assert metrics["out_degree"]["Machine"] == 1
        assert metrics["in_degree"]["Area"] == 1

    def test_no_relationships_returns_isolated_nodes(self, client):
        r = client.post("/api/graph/schema/build", json={"types": ["Machine", "Area"]})
        data = r.json()
        assert len(data["nodes"]) == 2
        assert data["links"] == []

    def test_empty_types_returns_empty_graph(self, client):
        r = client.post("/api/graph/schema/build", json={"types": []})
        data = r.json()
        assert data["nodes"] == []
        assert data["links"] == []

    def test_stats_field_present(self, client):
        r = client.post("/api/graph/schema/build", json={"types": TYPES})
        stats = r.json().get("stats", {})
        assert stats.get("nodes") == len(TYPES)

    def test_missing_types_field_returns_422(self, client):
        r = client.post("/api/graph/schema/build", json={})
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
#  POST /api/graph/schema/type-view
# ══════════════════════════════════════════════════════════════════════════════

class TestSchemaTypeView:

    def test_returns_ok_with_view(self, client):
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": RELATIONSHIPS_FULL,
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "view" in data

    def test_view_contains_type_id(self, client):
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": RELATIONSHIPS_FULL,
        })
        assert r.json()["view"]["type_id"] == "Machine"

    def test_from_rels_are_outgoing_relationships(self, client):
        """from_rels contiene las relaciones donde Machine es el origen."""
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": RELATIONSHIPS_FULL,
        })
        view = r.json()["view"]
        assert len(view["from_rels"]) == 1
        assert view["from_rels"][0]["to"] == "Area"

    def test_to_rels_are_incoming_relationships(self, client):
        """to_rels contiene las relaciones donde Machine es el destino."""
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": RELATIONSHIPS_FULL,
        })
        view = r.json()["view"]
        assert len(view["to_rels"]) == 1
        assert view["to_rels"][0]["from"] == "Plant"

    def test_type_with_no_relationships_has_empty_lists(self, client):
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Isolated",
            "relationships": RELATIONSHIPS_FULL,
        })
        view = r.json()["view"]
        assert view["from_rels"] == []
        assert view["to_rels"] == []

    def test_property_short_name_extracted(self, client):
        """property_short extrae el nombre corto de la IRI completa."""
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": [
                {"from": "Machine", "to": "Area", "property": "https://example.org/locatedIn", "implicit": False},
            ],
        })
        view = r.json()["view"]
        assert view["from_rels"][0]["property_short"] == "locatedIn"

    def test_implicit_flag_preserved_in_view(self, client):
        r = client.post("/api/graph/schema/type-view", json={
            "type_id": "Machine",
            "relationships": [
                {"from": "Machine", "to": "Area", "property": "locatedIn", "implicit": True},
            ],
        })
        view = r.json()["view"]
        assert view["from_rels"][0]["implicit"] is True

    def test_missing_type_id_returns_422(self, client):
        r = client.post("/api/graph/schema/type-view", json={"relationships": []})
        assert r.status_code == 422

    def test_no_relationships_param_accepted(self, client):
        """El campo relationships es opcional; sin él debe funcionar correctamente."""
        r = client.post("/api/graph/schema/type-view", json={"type_id": "Machine"})
        assert r.status_code == 200
        view = r.json()["view"]
        assert view["from_rels"] == []
        assert view["to_rels"] == []
