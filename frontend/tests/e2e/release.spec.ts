import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
async function complete(page: any, healthy = true) {
  await page
    .getByRole("button", { name: "Start sandbox run", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Begin health verification", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: healthy ? "Report healthy" : "Report failing health",
      exact: true,
    })
    .click();
  await expect(
    page.getByText(
      healthy
        ? "Sandbox artifact pointer committed."
        : "Active environment preserved.",
      { exact: !healthy },
    ),
  ).toBeVisible();
}
test("sign off, promote, export evidence and restore the previous successful artifact", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Know what’s/ }),
  ).toBeVisible();
  if (!process.env.DEMO_URL)
    await page.screenshot({
      path: fileURLToPath(new URL("../../../docs/entry.png", import.meta.url)),
      fullPage: true,
    });
  await page
    .getByRole("button", { name: "Open the sandbox", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: /v1.5.0/ })).toBeVisible();
  if (!process.env.DEMO_URL)
    await page.screenshot({
      path: fileURLToPath(
        new URL("../../../docs/workbench.png", import.meta.url),
      ),
      fullPage: true,
    });
  await page
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Signed off", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Queue production rehearsal", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Queue rehearsal", exact: true })
    .click();
  await complete(page);
  await expect(
    page.getByText("Sandbox artifact pointer committed.", { exact: false }),
  ).toBeVisible();
  if (!process.env.DEMO_URL)
    await page.screenshot({
      path: fileURLToPath(
        new URL("../../../docs/operation.png", import.meta.url),
      ),
      fullPage: true,
    });
  await page.getByRole("button", { name: "Close dialog" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Evidence JSON", exact: true }).click();
  expect((await download).suggestedFilename()).toBe(
    "releaselab-1.5.0-evidence.json",
  );
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  const prod = page.locator(".environments-grid .env-card.production");
  await expect(prod.locator(".env-version")).toContainText("v1.5.0");
  await prod
    .getByRole("button", { name: "Restore from history", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Queue restore rehearsal", exact: true })
    .click();
  await complete(page);
  await page.getByRole("button", { name: "Close dialog" }).click();
  await expect(prod.locator(".env-version")).toContainText("v1.4.0");
  await page.getByRole("button", { name: "Audit log", exact: true }).click();
  await expect(page.locator(".audit-list")).toContainText(
    "operation.succeeded",
  );
  await page.reload();
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(
    page.locator(".environments-grid .env-card.production .env-version"),
  ).toContainText("v1.4.0");
  if (!process.env.DEMO_URL) {
    await page.getByRole("button", { name: "Releases", exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: fileURLToPath(new URL("../../../docs/mobile.png", import.meta.url)),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
test("a candidate with failing health never replaces the active staging artifact", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Open the sandbox", exact: true })
    .click();
  await page
    .getByRole("button", { name: "New candidate", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Release notes", exact: true })
    .fill("A browser-created immutable candidate for a failure rehearsal.");
  await page
    .getByRole("button", { name: "Register candidate", exact: true })
    .last()
    .click();
  await expect(page.getByRole("heading", { name: /v1.7.0/ })).toBeVisible();
  await page
    .getByRole("button", { name: "Record evidence", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record evidence", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Queue staging rehearsal", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Queue rehearsal", exact: true })
    .click();
  await complete(page, false);
  await expect(
    page.getByText("Active environment preserved.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Environments", exact: true }).click();
  await expect(
    page.locator(".environments-grid .env-card.staging .env-version"),
  ).toContainText("v1.5.0");
});

test("expired-session response clears the old dialog before opening a new workspace", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Open the sandbox", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  const expired = "**/api/releases/*/approve";
  await page.route(expired, (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Your demo expired. Open a fresh workspace.",
      }),
    }),
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Open the sandbox", exact: true }),
  ).toBeVisible();
  await page.unroute(expired);
  await page
    .getByRole("button", { name: "Open the sandbox", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /v1.5.0/ })).toBeVisible();
  await page
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Record sign-off", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Signed off", exact: true }),
  ).toBeDisabled();
});
