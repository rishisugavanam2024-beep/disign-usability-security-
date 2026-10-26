// Application-owned Node.js permission check and test command. No dependencies.
const [workflow, ...removed] = process.argv.slice(2);
if (workflow !== 'read_orders') process.exit(2);
const permissions = new Set(['g_orders']);
for (const id of removed) {
  if (id !== 'g_orders') process.exit(2);
  permissions.delete(id);
}
const allowed = permissions.has('g_orders');
process.stdout.write(JSON.stringify({
  workflow_id: workflow, success: allowed,
  output: allowed ? 'orders:2' : 'forbidden',
  message: allowed ? 'HTTP:200' : 'HTTP:403',
  side_effects: {}, validation_errors: [],
  events: [{ workflow, identity: 'alice', resource: 'orders', action: 'read',
    allowed, grant_ids: allowed ? ['g_orders'] : [], checkpoint: 'orders:read' }]
}));
