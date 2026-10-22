// Run against a started Réplique server. The local model is simulated here;
// backend/test_accounts.py covers the real HTTP contract to that model.
import { chromium } from "playwright";
import assert from "node:assert/strict";

const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
const mode = process.argv[2] === "hosted" ? "hosted" : "local";
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  let registered = false;
  let credits = 20;
  let ocrAttempts = 0;
  let imageRequests = 0;
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let status = 200;
    let body = {};
    if (path === "/api/health") body = { mode, provider: mode === "hosted" ? "OpenAI" : "serveur Réplique", ocr_available: true, ocr_languages: ["fra"] };
    else if (path === "/api/account/status") {
      if (!registered) { status = 401; body = { detail: "Non connecté" }; }
      else body = { email: "beta@example.test", trial_remaining: credits, trial_total: 20, subscription_active: false, subscription_available: false };
    } else if (path === "/api/account/register") {
      registered = true;
      body = { email: "beta@example.test", trial_remaining: credits, trial_total: 20, subscription_active: false, subscription_available: false };
    } else if (path === "/api/generate" || path === "/api/generate-image") {
      if (path === "/api/generate-image") imageRequests++;
      credits--;
      body = { mode, notice: "Réponses Réplique.", insight: "Une réponse courte et libre.", boundary: false,
        replies: [
          { id: "1", title: "Simple", text: "On peut en reparler.", why: "Simple." },
          { id: "2", title: "Plus chaleureuse", text: "Ça me ferait plaisir.", why: "Chaleureux." },
          { id: "3", title: "Plus directe", text: "On se voit ?", why: "Direct." },
        ] };
    } else if (path === "/api/ocr") {
      ocrAttempts++;
      if (mode === "hosted") assert.match(route.request().postData() || "", /name="consent"\r?\n\r?\ntrue/);
      if (ocrAttempts === 1) { status = 422; body = { detail: "Aucun texte lisible n’a été détecté." }; }
      else body = { text: "Bonjour depuis la capture", warning: "Texte extrait. Relisez-le avant de continuer." };
    } else { status = 404; body = { detail: "Route absente" }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto(process.env.TEST_URL || "http://127.0.0.1:8000");
  await page.getByText("VOTRE COMPTE RÉPLIQUE").waitFor();
  assert.equal(await page.getByText("Continue with ChatGPT").count(), 0);
  if (mode === "hosted") {
    assert.equal(await page.getByText(/Réplique transmet les conversations confirmées à OpenAI/).count(), 0);
    assert.equal(await page.locator(".ocr-consent").count(), 0);
  }
  await page.getByRole("button", { name: "J’ai un code d’invitation" }).click();
  await page.getByLabel("Adresse e-mail").fill("beta@example.test");
  await page.getByLabel("Mot de passe").fill("une phrase assez longue");
  await page.getByLabel("Code d’invitation").fill("fake-test-invite");
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await page.getByText("20 crédits").waitFor();
  await page.locator(".memory-panel").waitFor();
  if (mode === "hosted") {
    assert.equal(await page.getByRole("button", { name: "Importer une capture" }).isEnabled(), true);
    const capture = { name: "capture.png", mimeType: "image/png", buffer: Buffer.from("mock image") };
    await page.locator('input[type="file"]').setInputFiles(capture);
    await page.locator(".selected-photo").waitFor();
    assert.equal(ocrAttempts, 0);
    assert.equal(await page.getByRole("button", { name: "Trouver mes mots" }).isDisabled(), true);
    await page.locator(".consent input").check();
    assert.equal(await page.getByRole("button", { name: "Trouver mes mots" }).isEnabled(), true);
  } else {
    const capture = { name: "capture.png", mimeType: "image/png", buffer: Buffer.from("mock image") };
    await page.locator('input[type="file"]').setInputFiles(capture);
    await page.locator(".context-sheet .error").getByText(/Aucun texte lisible/).waitFor();
    await page.getByRole("button", { name: "Réessayer la lecture" }).click();
    await page.waitForFunction(() => document.querySelector("#conversation")?.value.includes("Bonjour depuis la capture"));
    await page.locator(".ocr-note").getByText(/Relisez-le/).waitFor();
    assert.equal(ocrAttempts, 2);
    await page.locator("#conversation").click();
    await page.getByRole("button", { name: "Autre personne", exact: true }).click();
    assert.equal(await page.locator("#conversation").inputValue(), "Autre personne : Bonjour depuis la capture");
    await page.getByRole("button", { name: "Essayer un exemple" }).click();
    await page.getByLabel("J’ai relu le texte").check();
    await page.locator(".consent input").check();
  }
  await page.getByRole("button", { name: "Trouver mes mots" }).click();
  await page.locator(".reply").first().waitFor();
  assert.equal(await page.locator(".reply").count(), 3);
  await page.getByText("19 crédits").waitFor();
  if (mode === "hosted") assert.equal(imageRequests, 1);
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow ${width}`);
  }
  assert.deepEqual(errors, []);
  console.log(`PASS ${mode} beta browser: account, generation, credit display, responsive widths, no page errors. API/provider simulated.`);
} finally {
  await browser.close();
}
