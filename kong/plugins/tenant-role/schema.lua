-- kong/plugins/tenant-role/schema.lua
-- local typedefs = require "kong.db.schema.typedefs"

return {
  name = "tenant-role",
  fields = {
    {
      config = {
        type = "record",
        fields = {
          { tenant_header = { type = "string", required = true } },  -- Define como un string
        },
      },
    },
  },
}