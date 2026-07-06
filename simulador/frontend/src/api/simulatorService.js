import axios from 'axios';

// En desarrollo, Vite redirigirá esto al puerto de FastAPI
const apiClient = axios.create({
  baseURL: '/api',
});

export const getDevices = async () => {
  const response = await apiClient.get('/devices');
  return response.data;
};

export const addDevice = async (deviceConfig) => {
  const response = await apiClient.post('/devices', deviceConfig);
  return response.data;
};

export const uploadYaml = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await apiClient.post('/upload-yaml', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const getDeviceTree = async (deviceName) => {
  const response = await apiClient.get(`/devices/${deviceName}/tree`);
  return response.data;
};

export const createDevice = async (name) => {
  const response = await apiClient.post('/devices', { name });
  return response.data;
};

export const addVariableToDevice = async (deviceName, varConfig) => {
  const response = await apiClient.post(`/devices/${deviceName}/variables`, varConfig);
  return response.data;
};

export const deleteOpcuaNode = async (nodeId) => {
  const response = await apiClient.delete('/opcua/node', {
    data: { node_id: nodeId }
  });
  return response.data;
};

export const getFiwareTypes = async (fiwareConfig) => {
  const response = await apiClient.post(`/fiware/types`, fiwareConfig);
  return response.data;
};

export const getFiwareEntities = async (fiwareConfig, entityType = null) => {
  const payload = { config: fiwareConfig, entity_type: entityType };
  const response = await apiClient.post('/fiware/entities', payload);
  return response.data;
};

export const provisionFiwareDevice = async (mappingPayload) => {
  const response = await apiClient.post('/fiware/provision', mappingPayload);
  return response.data;
};

export const getFiwareEntityDetails = async (entityId, fiwareConfig) => {
  const response = await apiClient.post(`/fiware/entities/${entityId}`, fiwareConfig);
  return response.data;
};

export const exploreExternalOpcua = async (url) => {
  const response = await apiClient.post('/opcua/explore', { url });
  return response.data;
};