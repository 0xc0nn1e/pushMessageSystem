import Fastify from "fastify";

const app = Fastify({ logger: true });
const port = Number(process.env.PORT ?? 3000);

app.get("/health", async () => {
  return { ok: true };
});

app.listen({ port, host: "127.0.0.1" })
  .then(() => {
    app.log.info(`listening on http://127.0.0.1:${port}`);
  })
  .catch(err => {
    app.log.error(err);
    process.exit(1);
  });
