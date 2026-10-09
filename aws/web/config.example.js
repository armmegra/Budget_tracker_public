/* The instance this copy of the page talks to.
 *
 * Copy to config.js and fill in the three values. The Terraform frontend module
 * writes this file into the web bucket by itself; `terraform output` prints
 * the values when the page is served from somewhere else.
 *
 * None of the three is a secret: they travel in every sign-in request any
 * browser app makes. The password, and the second factor, are the secrets.
 */
window.BUDGET_CONFIG = {
  domain:   "https://<pool-domain>.auth.<region>.amazoncognito.com",
  clientId: "<app-client-id>",
  api:      "https://<api-id>.execute-api.<region>.amazonaws.com",
};
