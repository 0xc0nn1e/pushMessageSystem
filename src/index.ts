import http from "node:http";
const port = Number(process.env.PORT ?? 3000);
const server = http.createServer((req, res) => {
  if (req.url === "/health") { res.writeHead(200, {"content-type":"application/json"}); res.end(JSON.stringify({ok:true})); return; }
  res.writeHead(404, {"content-type":"application/json"}); res.end(JSON.stringify({ok:false}));
});
server.listen(port, "127.0.0.1", () => console.log(`listening on http://127.0.0.1:${port}`));
