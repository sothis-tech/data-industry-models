// public/config.js
// Este archivo NO pasa por el compilador de React. 
// Nginx lo servirá directamente y podremos sobrescribirlo desde Docker.
window.APP_CONFIG = {
    orion_url: "http://orion-ld:1026",
    iota_url: "http://iot-agent:4041",
    tenant: "ibermot",
    service_path: "/",
    apikey: "iot-ibermot",
    context_url: "http://context-provider/industrial-oven-context.jsonld",
    opcua_default_endpoint: "opc.tcp://opcua-linker-backend:5679"
};