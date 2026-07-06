# IoT Agent OPC UA: Dynamic Provisioning Guide

This guide explains how to use the IoT Agent in **Dynamic Mode** to provision devices from one or multiple OPC UA servers at runtime via the REST API.

## 1. Overview of Dynamic Mode
In `dynamic` mode, the IoT Agent does not load a static configuration file at startup. Instead, it relies entirely on the **Provisioning API** to define which devices to monitor, which OPC UA servers to connect to, and how to map OPC UA nodes to Orion Context Broker attributes.

### Enabling Dynamic Mode
Set the following environment variable in your `docker-compose.yml` or environment config:
```yaml
CONFIGURATION_TYPE=dynamic
```

---

## 2. Provisioning Devices
To add a device to the agent, you must send a `POST` request to the `/iot/devices` endpoint.

**Endpoint:** `POST http://<iot-agent-host>:4041/iot/devices`

### Request Payload Structure
The payload must be a JSON object containing a list of devices.

| Field | Description |
| :--- | :--- |
| `device_id` | Unique identifier for the device within the agent. |
| `entity_name` | The name of the entity that will be created in the Orion Context Broker. |
| `entity_type` | The type of the entity in Orion (e.g., `"Device"`). |
| `apikey` | The API key used for the service. |
| `endpoint` | **Crucial:** The OPC UA server URL (e.g., `opc.tcp://opcua-sim-v2:5679`). |
| `attributes` | List of attributes to be created in Orion. |
| `internal_attributes.contexts` | Mapping definitions that link Orion attributes to OPC UA Node IDs. |

### Detailed Mapping (`contexts`)
The `mappings` array inside the context defines exactly which OPC UA node corresponds to which Orion attribute:
- `ocb_id`: The name of the attribute in the Context Broker.
- `opcua_id`: The Node ID of the variable on the OPC UA server (e.g., `ns=2;i=2`).
- `object_id`: A reference identifier for the object.

---

## 3. Provisioning from Different Servers
The IoT Agent now supports **multi-server connectivity**. You can provision multiple devices, each pointing to a different `endpoint`.

**How it works:**
1. When a device is provisioned, the agent checks if a connection to that specific `endpoint` already exists.
2. If not, it automatically establishes a new connection, creates a session, and starts a subscription for that server.
3. The agent maintains a separate session for each unique server URL, allowing it to aggregate data from a diverse industrial landscape into a single Orion instance.

### Example: Provisioning two devices from two different servers

```bash
curl -X POST http://localhost:4041/iot/devices \
-H "Content-Type: application/json" \
-d '{
  "devices": [
    {
      "device_id": "PLC_SENSORS_01",
      "entity_name": "factory_plc_1",
      "entity_type": "Device",
      "apikey": "iot",
      "endpoint": "opc.tcp://server-alpha:5679",
      "attributes": [{ "name": "temperature", "type": "Double" }],
      "internal_attributes": {
        "contexts": [{
          "id": "PLC_SENSORS_01",
          "type": "Device",
          "mappings": [{ "ocb_id": "temperature", "opcua_id": "ns=2;i=10", "object_id": "temp_sensor" }]
        }]
      }
    },
    {
      "device_id": "PLC_SENSORS_02",
      "entity_name": "factory_plc_2",
      "entity_type": "Device",
      "apikey": "iot",
      "endpoint": "opc.tcp://server-beta:5679",
      "attributes": [{ "name": "pressure", "type": "Double" }],
      "internal_attributes": {
        "contexts": [{
          "id": "PLC_SENSORS_02",
          "type": "Device",
          "mappings": [{ "ocb_id": "pressure", "opcua_id": "ns=3;i=50", "object_id": "press_sensor" }]
        }]
      }
    }
  ]
}'
```

---

## 4. Verification & Troubleshooting

### Checking Logs
Monitor the agent logs to ensure connections are established and nodes are added to the monitoring pool:
- **Success:** Look for `Connected to the OPCUA Server at <url>` and `<node_id> added to the monitoring pool!`.
- **Failure:** Look for `No Connection to the OPC UA Server` or `node refers to a node that does not exist`.

### Verifying in Orion
Since the agent only sends data when a value changes (or upon the first successful read), you can verify the entity creation by querying Orion:
```bash
curl -X GET http://localhost:1026/ngsi-ld/v1/entities/factory_plc_1
```

### Common Issues
- **Firewall/Network**: Ensure the agent container can reach the OPC UA server's IP and port.
- **Node IDs**: Ensure the `opcua_id` matches exactly what is defined in the OPC UA server address space.
- **Permissions**: Ensure the `username` and `password` provided in the environment variables (if any) have read access to the requested nodes.
