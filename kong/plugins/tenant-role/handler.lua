-- kong/plugins/tenant-role/handler.lua
local Plugin = {
  PRIORITY = 1000,
  VERSION = "1.0",
}

function Plugin:access(config)
  -- Añadir traza inicial de acceso
  kong.log.debug("Tenant-role plugin access phase started.")

  -- Obtiene el encabezado Authorization
  local authorization_header = kong.request.get_header("Authorization")
  if not authorization_header then
    kong.log.warn("Authorization header is missing.")
    return kong.response.exit(401, { message = "No Authorization header found" })
  end

  -- Asegúrate de que el header esté en el formato correcto
  local _, _, token = string.find(authorization_header, "Bearer%s+(.+)")
  if not token then
    kong.log.warn("Not a valid Authorization header for Bearer token.")
    return kong.response.exit(401, { message = "Invalid Authorization header" })
  else
    kong.log.debug("Authorization header token: ", token)
  end

  -- Descodifica el token usando resty.jwt 
  local jwt = require "resty.jwt"
  local obj = jwt:load_jwt(token)
  if not obj.valid then
    return kong.response.exit(401,{message="Invalid JWT"})
  end

  -- Obtiene el payload JWT
  local jwt_payload = obj.payload
  if not jwt_payload then
    kong.log.warn("No JWT payload found in request.")
    return kong.response.exit(401, { message = "No JWT payload" })
  end

  local roles = jwt_payload["realm_access"] and jwt_payload["realm_access"]["roles"] or {}

  -- Log los roles obtenidos
  kong.log.debug("Roles found in JWT: ", require("cjson").encode(roles))

  -- Obtiene el encabezado de tenant
  local tenant = kong.request.get_header("NGSILD-Tenant")
  if not tenant then
    kong.log.warn("NGSILD-Tenant header is missing from the request.")
    return kong.response.exit(400, { message = "NGSILD-Tenant header is missing" })
  end

  -- Log el valor del encabezado de tenant
  kong.log.debug("NGSILD-Tenant header value: ", tenant)

  -- Define el rol esperado basado en el tenant
  local expected_role = "tenant_" .. tenant
  kong.log.debug("Expected role to check: ", expected_role)

  local has_role = false
  for _, role in ipairs(roles) do
    kong.log.debug("Checking against role: ", role)  -- Log para cada rol en el JWT
    if role == expected_role then
      has_role = true
      kong.log.debug("User has the expected role for tenant: ", expected_role)
      break
    end
  end

  if not has_role then
    kong.log.warn("User lacks role for tenant: ", tenant)
    return kong.response.exit(403, { message = "User lacks role for tenant: " .. tenant })
  end

  -- Finaliza con éxito
  kong.log.debug("Access granted for user with tenant: ", tenant)

end

return Plugin