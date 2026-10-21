// Requires running API + built frontend on http://127.0.0.1:8000.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_PATH
    ? { executablePath: process.env.CHROMIUM_PATH }
    : {}),
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.env.TEST_URL || "http://127.0.0.1:8000");
  await page.getByText("Démo · exemples préécrits", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Essayer un exemple" }).click();
  await page.getByLabel("J’ai relu le texte").check();
  await page.getByRole("button", { name: "Trouver mes mots" }).click();
  await page.locator(".reply").first().waitFor();
  assert.equal(await page.locator(".reply").count(), 3);
  await page
    .getByLabel("Modifier la réponse 1")
    .fill("Ma réponse personnelle.");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter" }).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "replique-reponses.txt");
  await mkdir("../evidence", { recursive: true });
  await page.screenshot({ path: "../evidence/desktop.png", fullPage: true });
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      "no horizontal overflow at " + width,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../evidence/mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Effacer la session et commencer une nouvelle conversation" }).click();
  assert.match(await page.getByLabel("Votre conversation", { exact: true }).inputValue(), /Autre personne/);
  await page.getByRole("button", { name: "Effacer et recommencer" }).click();
  assert.equal(
    await page.getByLabel("Votre conversation", { exact: true }).inputValue(),
    "",
  );
  assert.equal(await page.locator(".reply").count(), 0);
  assert.deepEqual(errors, []);
  console.log(
    "PASS: actual browser generation, edit, export, responsive overflow, reset, console.",
  );
} finally {
  await browser.close();
}
