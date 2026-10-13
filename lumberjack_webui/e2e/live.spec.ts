import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";

test.describe("real backend", () => {
  test.skip(
    !process.env.LUMBERJACK_E2E_LIVE,
    "Set LUMBERJACK_E2E_LIVE=1 against a running backend.",
  );
  test("Markdown, records and DOCX complete the real pipeline", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText("服务可达", { exact: true })).toBeVisible();
    for (const [format, text] of [
      [
        "markdown",
        "# Live document\n\nHello from the real pipeline.\n\n## More\n\nAnother paragraph.",
      ],
      ["csv", "name,region\napi-gateway,us-east-1\nauth-service,eu-west-1\n"],
      ["jsonl", '{"id":1,"name":"API"}\n{"id":2,"name":"Auth"}\n'],
    ]) {
      await page.getByRole("tab", { name: "文档输入", exact: true }).click();
      await page
        .getByRole("textbox", { name: "文档输入", exact: true })
        .fill(text);
      await page.getByLabel("输入格式", { exact: true }).selectOption(format);
      await page
        .getByRole("button", { name: "调整参数", exact: true })
        .first()
        .click();
      await page
        .getByLabel("切分器", { exact: true })
        .selectOption(format === "markdown" ? "section" : "record");
      await page.getByRole("button", { name: "完成", exact: true }).click();
      const response = page.waitForResponse("**/lumber/api/split/text");
      await page.getByRole("button", { name: "运行分割", exact: true }).click();
      const data = await response;
      expect(data.status()).toBe(200);
      const body = await data.json();
      expect(body.schema_version).toBeTruthy();
      expect(body.chunks.length).toBeGreaterThan(0);
      await expect(
        page.getByRole("tab", { name: "分割预览", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
    }
    await page.getByRole("tab", { name: "文档输入", exact: true }).click();
    await page
      .locator('input[type="file"]')
      .setInputFiles(
        fileURLToPath(
          new URL("../../tests/fixtures/docx/sample.docx", import.meta.url),
        ),
      );
    await page.getByLabel("输入格式", { exact: true }).selectOption("docx");
    await page
      .getByRole("button", { name: "调整参数", exact: true })
      .first()
      .click();
    await page.getByLabel("切分器", { exact: true }).selectOption("section");
    await page.getByRole("button", { name: "完成", exact: true }).click();
    const response = page.waitForResponse("**/lumber/api/split/file");
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(
      page.getByRole("button", { name: "原文行范围", exact: true }),
    ).toHaveCount(0);
    await page.screenshot({ path: "test-results/live-docx.png" });
  });
});
