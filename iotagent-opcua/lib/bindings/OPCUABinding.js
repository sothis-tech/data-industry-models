/*
 * Copyright 2022 Engineering Ingegneria Informatica S.p.A.
 *
 * This file is part of iotagent-opcua
 *
 * iotagent-opcua is free software: you can redistribute it and/or
 * modify it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the License,
 * or (at your option) any later version.
 *
 * iotagent-opcua is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License along with iotagent-opcua.
 * If not, see http://www.gnu.org/licenses/.
 *
 * For those usages not covered by the GNU Affero General Public License
 * please contact with::[manfredi.pistone@eng.it, gabriele.deluca@eng.it, walterdomenico.vergara@eng.it, mattiagiuseppe.marzano@eng.it]
 */

/* eslint-disable no-unused-vars */

const opcua = require('node-opcua');
const opcuaTypes = require('node-opcua-types');
const async = require('async');
const fs = require('fs');
const os = require('os');
const path = require('path');
const moment = require('moment');
const commonBindings = require('../commonBindings');
const metaBindings = require('../metaBindings');
const context = {
    op: 'IoTAgentOPCUA.OPCUABinding'
};
const config = require('../configService');
const { FORBIDDEN_NGSI_CHARS } = require('../constants');

const sessions = new Map();
const subscriptions = new Map();
const clients = new Map();

/**
 * Helper to get or create a session and subscription for a given endpoint.
 * @param {string} endpoint 
 * @returns {Promise<{session, subscription}>}
 */
async function getOrCreateSession(endpoint) {
    if (sessions.has(endpoint)) {
        return { session: sessions.get(endpoint), subscription: subscriptions.get(endpoint) };
    }

    try {
        const opcuaSecurityMode = opcua.MessageSecurityMode[config.getConfig().opcua.securityMode];
        const opcuaSecurityPolicy = opcua.SecurityPolicy[config.getConfig().opcua.securityPolicy];

        const opcUAClientOptions = {
            endpointMustExist: false,
            securityMode: opcuaSecurityMode,
            securityPolicy: opcuaSecurityPolicy,
            defaultSecureTokenLifetime: 400000,
            keepSessionAlive: true,
            requestedSessionTimeout: 100000,
            connectionStrategy: {
                maxRetry: 10,
                initialDelay: 2000,
                maxDelay: 10 * 1000
            }
        };

        const certificateFolder = path.join(process.cwd(), '/certificates');
        const certificateFile = path.join(certificateFolder, 'server_certificate.pem');

        const certificateManager = new opcua.OPCUACertificateManager({
            rootFolder: certificateFolder,
            name: ''
        });
        await certificateManager.initialize();

        const privateKeyFile = certificateManager.privateKey;
        if (!fs.existsSync(certificateFile)) {
            await certificateManager.createSelfSignedCertificate({
                subject: '/CN=localhost/O=Engineering Ingegneria Informatica S.p.A./L=Palermo',
                startDate: new Date(),
                dns: [],
                validity: 365 * 5,
                applicationUri: `urn:${os.hostname()}:NodeOPCUA-Client`,
                outputFile: certificateFile
            });
        }

        const resolvedCertificateFilePath = path.resolve(certificateFile).replace(/\\/g, '/');
        const resolvedPrivateKeyFilePath = path.resolve(privateKeyFile).replace(/\\/g, '/');
        opcUAClientOptions.certificateFile = resolvedCertificateFilePath;
        opcUAClientOptions.privateKeyFile = resolvedPrivateKeyFilePath;
        opcUAClientOptions.clientCertificateManager = certificateManager;

        const client = opcua.OPCUAClient.create(opcUAClientOptions);
        await client.connect(endpoint);
        config.getLogger().info(context, 'Connected to the OPCUA Server at ' + endpoint);

        client.on('backoff', (retry, delay) => config.getLogger().info('still trying to connect to ' + endpoint + ': retry = ' + retry + ' next attempt in ' + delay / 1000 + ' seconds'));

        const username = config.getConfig().opcua.username;
        const password = config.getConfig().opcua.password;
        let userIdentity = null;

        if (username && password) {
            userIdentity = {
                userName: username,
                password: password,
                type: opcuaTypes.UserTokenType.UserName
            };
        }

        const session = await client.createSession(userIdentity);
        
        client
            .on('connection_reestablished', () => config.getLogger().info(context, 'CONNECTION RESTABLISHED for ' + endpoint))
            .on('after_reconnection', (err) => config.getLogger().info(context, '... reconnection process completed for ' + endpoint + ': ' + err))
            .on('close', (err) => config.getLogger().info(context, 'Check Security Settings for ' + endpoint + ' ' + err))
            .on('backoff', (nb, delay) => config.getLogger().error(context, 'connection failed for ' + endpoint + ' the ' + nb + ' time ... We will retry in ' + delay + ' ms'))
            .on('start_reconnection', () => config.getLogger().error(context, 'start_reconnection not working for ' + endpoint + ' so aborting'));

        const subscriptionOptions = {
            maxNotificationsPerPublish: config.getConfig().opcua.subscription.maxNotificationsPerPublish,
            publishingEnabled: config.getConfig().opcua.subscription.publishingEnabled,
            requestedLifetimeCount: config.getConfig().opcua.subscription.requestedLifetimeCount,
            requestedMaxKeepAliveCount: config.getConfig().opcua.subscription.requestedMaxKeepAliveCount,
            requestedPublishingInterval: config.getConfig().opcua.subscription.requestedPublishingInterval,
            priority: config.getConfig().opcua.subscription.priority
        };

        const subscription = await session.createSubscription2(subscriptionOptions);
        subscription
            .on('started', () => config.getLogger().info(context, 'subscription started for ' + endpoint + ' - subscriptionId=' + subscription.subscriptionId))
            .on('keepalive', () => config.getLogger().info(context, 'subscription keepalive for ' + endpoint))
            .on('terminated', () => config.getLogger().info(context, 'subscription terminated for ' + endpoint));

        clients.set(endpoint, client);
        sessions.set(endpoint, session);
        subscriptions.set(endpoint, subscription);

        return { session, subscription };
    } catch (err) {
        config.getLogger().error(context, 'Failed to establish connection to ' + endpoint + ': ' + err.message);
        throw err;
    }
}

/**
 * Read variable value from OPCUA Server
 * @param {string} endpoint
 * @param {string} opcuaNodeId
 * @returns value of the variable
 */
async function readValueFromOPCUANode(endpoint, opcuaNodeId) {
    try {
        const { session } = await getOrCreateSession(endpoint);
        const dataValue = await session.readVariableValue(opcuaNodeId);
        if (dataValue.value == null) {
            return null;
        } else {
            config.getLogger().info(context, opcuaNodeId + ' read variable -> ' + dataValue.toString());
            return dataValue.value.value;
        }
    } catch (err) {
        config.getLogger().error(context, 'Error reading node ' + opcuaNodeId + ' from ' + endpoint + ': ' + err.message);
        return null;
    }
}

/**
 * Read variable value type from OPCUA Server
 * @param {string} endpoint
 * @param {string} opcuaNodeId
 * @returns value type of the variable
 */
async function readValueTypeFromOPCUANode(endpoint, opcuaNodeId) {
    try {
        const { session } = await getOrCreateSession(endpoint);
        const dataValue = await session.readVariableValue(opcuaNodeId);
        if (dataValue.value == null) {
            return null;
        } else {
            config.getLogger().info(context, opcuaNodeId + ' read variable type -> ' + dataValue.toString());
            return dataValue.value.dataType;
        }
    } catch (err) {
        config.getLogger().error(context, 'Error reading type for node ' + opcuaNodeId + ' from ' + endpoint + ': ' + err.message);
        return null;
    }
}

/**
 * Check if OPCUA node exist and return results array
 * @param {string} endpoint
 * @param {string} opcuaNodeId
 * @returns results array
 */
async function doesOPCUANodeExist(endpoint, opcuaNodeId) {
    try {
        const { session } = await getOrCreateSession(endpoint);
        
        // En lugar de usar session.browse (que busca hijos y falla en variables hoja),
        // leemos el atributo NodeClass. Todos los nodos válidos tienen este atributo.
        const nodeToRead = {
            nodeId: opcuaNodeId,
            attributeId: opcua.AttributeIds.NodeClass
        };
        
        const dataValue = await session.read(nodeToRead);
        
        return [{ statusCode: dataValue.statusCode }];
        
    } catch (err) {
        config.getLogger().error(context, 'Error checking existence of node ' + opcuaNodeId + ' at ' + endpoint + ': ' + err.message);
        return null;
    }
}

/**
 * Start monitoring OPCUA attributes
 */
async function startMonitoring() {
    const contexts = config.getConfig().iota.contexts || [];
    for (const opcuaServerConfigContext of contexts) {
        const endpoint = opcuaServerConfigContext.endpoint;
        if (!endpoint) {
            config.getLogger().error(context, 'No endpoint specified for context ' + opcuaServerConfigContext.id);
            continue;
        }

        try {
            const { subscription } = await getOrCreateSession(endpoint);
            for (const mapping of opcuaServerConfigContext.mappings) {
                const opcua_id = mapping.opcua_id;
                const results = await doesOPCUANodeExist(endpoint, opcua_id);
                if (results && results.length > 0) {
                    const result = results[0];
                    if (result.statusCode == opcua.StatusCodes.Good) {
                        if (config.getConfig().iota.events && config.getConfig().iota.events.find((obj) => obj.opcua_id === mapping.opcua_id)) {
                            const itemToMonitor = {
                                nodeId: opcua.resolveNodeId(opcua_id),
                                attributeId: opcua.AttributeIds.EventNotifier
                            };
                            const fields = config.getConfig().iota.events.find((obj) => obj.opcua_id === mapping.opcua_id).fields;
                            const eventFilter = opcua.constructEventFilter(fields);
                            const monitoringParamaters = {
                                samplingInterval: 100,
                                discardOldest: true,
                                filter: eventFilter,
                                queueSize: 10
                            };
                            try {
                                const monitoredItem = await subscription.monitor(itemToMonitor, monitoringParamaters, opcua.TimestampsToReturn.Both);
                                config.getLogger().info(context, opcua_id + ' added to the monitoring pool!');
                                
                                monitoredItem.on('changed', function (dataValue) {
                                    
                                    // --- INICIO DE NUESTRO LOG ESPIA ---
                                    console.log("\n\n🚨 [DEBUG FIWARE] EVENTO RECIBIDO DESDE OPC UA 🚨");
                                    console.log(" -> Nodo Origen (opcua_id):", opcua_id);
                                    console.log(" -> Mapeo destino (mapping):", JSON.stringify(mapping));
                                    if (dataValue && dataValue.value) {
                                        console.log(" -> Valor capturado (dataValue.value.value):", dataValue.value.value);
                                        console.log(" -> Tipo de dato capturado:", dataValue.value.dataType);
                                        console.log(" -> Timestamp capturado:", dataValue.sourceTimestamp);
                                    } else {
                                        console.log(" -> ¡ALERTA! dataValue.value viene vacío o nulo.");
                                    }
                                    console.log("----------------------------------------------------\n\n");
                                    // --- FIN DE NUESTRO LOG ESPIA ---

                                    if (dataValue.statusCode.valueOf() == 0) {
                                        if (dataValue.value.dataType === opcua.DataType.UInt64) {
                                            if (Array.isArray(dataValue.value.value) && dataValue.value.value.length === 2) {
                                                const msb = dataValue.value.value[0];
                                                const lsb = dataValue.value.value[1];
                                                const value = ((msb << 32) | lsb) >>> 0;
                                                commonBindings.opcuaMessageHandler(opcuaServerConfigContext.id, mapping, value, dataValue.sourceTimestamp);
                                            }
                                        } else {
                                            config.getLogger().info(context, opcua_id + ' value changed -> ' + dataValue.value.value);
                                            // ESTA ES LA LÍNEA CRÍTICA DONDE SE MANDA A ORION:
                                            commonBindings.opcuaMessageHandler(opcuaServerConfigContext.id, mapping, dataValue.value.value, dataValue.sourceTimestamp);
                                        }
                                    } else {
                                        config.getLogger().error(context, opcua_id + ' value change error');
                                    }
                                });
                            } catch (err) {
                                config.getLogger().error(context, 'Error monitoring value for node ' + opcua_id + ': ' + err.message);
                            }
                        } else {
                            const itemToMonitor = {
                                nodeId: opcua.resolveNodeId(opcua_id),
                                attributeId: opcua.AttributeIds.Value
                            };
                            const monitoringParamaters = {
                                samplingInterval: 100,
                                discardOldest: true,
                                queueSize: 10
                            };
                            try {
                                const monitoredItem = await subscription.monitor(itemToMonitor, monitoringParamaters, opcua.TimestampsToReturn.Both);
                                config.getLogger().info(context, opcua_id + ' added to the monitoring pool!');
                                monitoredItem.on('changed', function (dataValue) {
                                    if (dataValue.statusCode.valueOf() == 0) {
                                        if (dataValue.value.dataType === opcua.DataType.UInt64) {
                                            if (Array.isArray(dataValue.value.value) && dataValue.value.value.length === 2) {
                                                const msb = dataValue.value.value[0];
                                                const lsb = dataValue.value.value[1];
                                                const value = ((msb << 32) | lsb) >>> 0;
                                                commonBindings.opcuaMessageHandler(opcuaServerConfigContext.id, mapping, value, dataValue.sourceTimestamp);
                                            }
                                        } else {
                                            config.getLogger().info(context, opcua_id + ' value changed -> ' + dataValue.value.value);
                                            commonBindings.opcuaMessageHandler(opcuaServerConfigContext.id, mapping, dataValue.value.value, dataValue.sourceTimestamp);
                                        }
                                    } else {
                                        config.getLogger().error(context, opcua_id + ' value change error');
                                    }
                                });
                            } catch (err) {
                                config.getLogger().error(context, 'Error monitoring value for node ' + opcua_id + ': ' + err.message);
                            }
                        }
                    }
                }
            }
        } catch (err) {
            config.getLogger().error(context, 'Error starting monitoring for context ' + opcuaServerConfigContext.id + ': ' + err.message);
        }
    }
}

async function terminateAllSessions() {
    for (const [endpoint, subscription] of subscriptions) {
        try {
            await subscription.terminate();
        } catch (err) {
            config.getLogger().error(context, 'Error terminating subscription for ' + endpoint + ': ' + err.message);
        }
    }
}

async function closeAllSessions() {
    for (const [endpoint, session] of sessions) {
        try {
            await session.close();
        } catch (err) {
            config.getLogger().error(context, 'Error closing session for ' + endpoint + ': ' + err.message);
        }
    }
}

function prepareInputArguments(attribute) {
    const inputs = [];
    try {
        if (Array.isArray(attribute.value)) {
            config.getLogger().info(context, 'Found an Array as command input');
            for (const singleValue of attribute.value) {
                inputs.push(singleValue);
            }
        } else {
            inputs.push(attribute.value);
            config.getLogger().info(context, 'Command input not an array. Considering it as a single value');
        }
    } catch (e) {
        inputs.push(attribute.value);
        config.getLogger().warn(context, 'Unable to determine the type of the command input, considering it as a single value');
    }
    return inputs;
}

async function executeCommand(apiKey, device, attribute, serialized, contentType, callback) {
    const endpoint = device.endpoint;
    if (!endpoint) {
        config.getLogger().error(context, 'No endpoint specified for device ' + device.id);
        return null;
    }

    try {
        const { session } = await getOrCreateSession(endpoint);
        let foundMapping = {};
        for (const contextSubscription of config.getConfig().iota.contextSubscriptions) {
            for (const mapping of contextSubscription.mappings) {
                if (mapping.ocb_id === attribute.name) {
                    foundMapping = mapping;
                    break;
                }
            }
        }

        const inputs = prepareInputArguments(attribute);
        for (let i = 0; i < foundMapping.inputArguments.length; i++) {
            foundMapping.inputArguments[i].value = inputs[i];
        }

        const methodsToCall = [{
            objectId: String(foundMapping.object_id),
            methodId: String(foundMapping.opcua_id),
            inputArguments: foundMapping.inputArguments
        }];
        config.getLogger().info(context, 'Method to call =' + JSON.stringify(methodsToCall));

        const commandsResults = await session.call(methodsToCall);
        if (commandsResults.length > 0) {
            const thisCommand = commandsResults[0];
            return {
                attributeName: attribute.name,
                statusCode: thisCommand.statusCode.value,
                resultValue: thisCommand.outputArguments[0].dataType < 12 ? thisCommand.outputArguments[0].value : thisCommand.outputArguments[0].value[0]
            };
        } else {
            throw new Error('COMMAND-001: Error during command execution: commandResults.length is null');
        }
    } catch (err) {
        config.getLogger().error(context, 'Error executing command ' + attribute.name + ' on ' + endpoint + ': ' + err.message);
        return null;
    }
}

async function executeUpdate(apiKey, device, attribute, serialized, contentType, callback) {
    const endpoint = device.endpoint;
    if (!endpoint) {
        config.getLogger().error(context, 'No endpoint specified for device ' + device.id);
        return null;
    }

    try {
        const { session } = await getOrCreateSession(endpoint);
        let foundMapping = {};
        for (const context of config.getConfig().iota.contexts) {
            for (const mapping of context.mappings) {
                if (mapping.ocb_id === attribute.name) {
                    foundMapping = mapping;
                    break;
                }
            }
        }
        if (Object.keys(foundMapping).length === 0) {
            for (const context of config.getConfig().iota.contextSubscriptions) {
                for (const mapping of context.mappings) {
                    if (mapping.ocb_id === attribute.name) {
                        foundMapping = mapping;
                        break;
                    }
                }
            }
        }

        const valueType = await readValueTypeFromOPCUANode(endpoint, foundMapping.opcua_id);
        const nodesToWrite = [{
            nodeId: foundMapping.opcua_id,
            attributeId: opcua.AttributeIds.Value,
            indexRange: null,
            value: {
                value: {
                    dataType: valueType,
                    value: attribute.value
                }
            }
        }];
        config.getLogger().info(context, 'Update to execute =' + JSON.stringify(nodesToWrite));

        const updateResults = await session.write(nodesToWrite);
        if (updateResults.length > 0) {
            const thisUpdate = updateResults[0];
            return {
                attributeName: attribute.name,
                statusCode: thisUpdate._name,
                resultValue: thisUpdate._description
            };
        } else {
            throw new Error('UPDATE-001: Error during update execution: updateResults.length is null');
        }
    } catch (err) {
        config.getLogger().error(context, 'Error executing update ' + attribute.name + ' on ' + endpoint + ': ' + err.message);
        return null;
    }
}

async function executeQuery(apiKey, device, attribute, callback) {
    const endpoint = device.endpoint;
    if (!endpoint) {
        config.getLogger().error(context, 'No endpoint specified for device ' + device.id);
        return null;
    }

    const type = device.type;
    const id = device.id;
    const contextElement = { type, id };

    let attributeType = 'string';
    let lazySet = [];

    if (device.lazy) {
        lazySet = device.lazy;
    } else if (config.getConfig().iota.types[type] && config.getConfig().iota.types[type].lazy) {
        lazySet = config.getConfig().iota.types[type].lazy;
    }

    const lazyObject = lazySet.find((lazyAttribute) => lazyAttribute.name === attribute);
    if (!lazyObject) {
        config.getLogger().fatal(context, "QUERY-002: Query execution could not be handled, as lazy attribute [%s] wasn't found", attribute);
        throw new Error("QUERY-002: Query execution could not be handled, as lazy attribute wasn't found");
    }

    attributeType = lazyObject.type;
    let foundMapping = {};
    for (const context of config.getConfig().iota.contextSubscriptions) {
        for (const mapping of context.mappings) {
            if (mapping.ocb_id === attribute) {
                foundMapping = mapping;
                break;
            }
        }
    }
    const value = await readValueFromOPCUANode(endpoint, foundMapping.opcua_id);
    contextElement[attribute] = {
        type: attributeType,
        value
    };

    return contextElement;
}

function deviceProvisioningHandler(device, callback) {
    callback(null, device);
}

function deviceUpdatingHandler(device, callback) {
    callback(null, device);
}

async function start() {
    if (!config.getConfig().opcua) {
        config.getLogger().fatal(context, 'GLOBAL-002: Configuration error. Configuration object [config.opcua] is missing');
        throw new Error('GLOBAL-002: Configuration error. Configuration object [config.opcua] is missing');
    }

    // Default connection attempt
    const defaultEndpoint = config.getConfig().opcua.endpoint;
    if (defaultEndpoint) {
        try {
            await getOrCreateSession(defaultEndpoint);
        } catch (err) {
            if (config.getConfig().configurationType === 'dynamic') {
                config.getLogger().warn(context, 'Could not connect to default endpoint ' + defaultEndpoint + ', but we are in dynamic mode, so we will continue.');
            } else {
                config.getLogger().fatal(context, 'Failed to connect to default endpoint ' + defaultEndpoint + ': ' + err.message);
                throw err;
            }
        }
    }

    await initProvisioning();
    await startMonitoring();
}

async function initProvisioning() {
    try {
        if (config.getConfig().configurationType === 'auto' || config.getConfig().configurationType === 'static') {
            await metaBindings.performProvisioning();
        }
    } catch (err) {
        config.getLogger().error(context, 'Error during initProvisioning: ' + err.message);
    }
}

async function stop() {
    config.getLogger().info(context, 'Gracefully stopping IotAgent');
    try {
        await terminateAllSessions();
        await closeAllSessions();
        for (const client of clients.values()) {
            client.disconnect();
        }
    } catch (err) {
        config.getLogger().error(context, 'Error during stop: ' + err.message);
    }
}

exports.deviceProvisioningHandler = deviceProvisioningHandler;
exports.deviceUpdatingHandler = deviceUpdatingHandler;
exports.executeCommand = executeCommand;
exports.executeUpdate = executeUpdate;
exports.executeQuery = executeQuery;
exports.readValueFromOPCUANode = readValueFromOPCUANode;
exports.readValueTypeFromOPCUANode = readValueTypeFromOPCUANode;
exports.doesOPCUANodeExist = doesOPCUANodeExist;
exports.start = start;
exports.stop = stop;
exports.startMonitoring = startMonitoring;
exports.protocol = 'OPCUA';
