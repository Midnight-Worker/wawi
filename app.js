import express from "express";
const app = express();

app.use(express.static("public"))
/*
app.get("/", (req, res) => {
  res.send("WAWI online!");
});
*/
app.listen(3333, () => {
  console.log("App läuft auf Port 3333");
});

