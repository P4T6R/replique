// Requires the built frontend and a running API with local Tesseract on 127.0.0.1:8000.
import { chromium } from "playwright";
import assert from "node:assert/strict";

const browser = await chromium.launch({ headless: true,
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(process.env.TEST_URL || "http://127.0.0.1:8000");
  await page.getByRole("button", { name: "Importer une capture" }).waitFor();
  const draft = "Moi : Je voudrais répondre à ce message.";
  const conversation = page.getByLabel("Votre conversation", { exact: true });
  await conversation.fill(draft);
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    canvas.height = 280;
    const context = canvas.getContext("2d");
    context.fillStyle = "white";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "black";
    context.font = "48px sans-serif";
    context.fillText("Moi : Salut", 40, 90);
    context.fillText("Autre personne : Bonjour, comment vas-tu ?", 40, 185);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  let first = true;
  await page.route("**/api/ocr", route => {
    if (first) {
      first = false;
      return route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ detail: "Lecture temporairement indisponible." }) });
    }
    return route.continue();
  });
  await page.locator('input[type="file"]').setInputFiles({ name: "capture.png", mimeType: "image/png",
    buffer: Buffer.from(png, "base64") });
  await page.getByRole("alert").filter({ hasText: "Lecture temporairement indisponible." }).waitFor();
  assert.equal(await conversation.inputValue(), draft);
  await page.getByRole("button", { name: "Réessayer la lecture" }).click();
  await page.waitForFunction(() => document.querySelector("#conversation")?.value.includes("Bonjour"));
  assert.match(await conversation.inputValue(), /Bonjour/);
  assert.equal(await page.getByLabel("J’ai relu le texte").isChecked(), false);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  console.log("PASS mobile browser: failed upload keeps draft; retry extracts real PNG text and requires review.");
} finally {
  await browser.close();
}
