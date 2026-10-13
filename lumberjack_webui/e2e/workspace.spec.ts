import { test, expect, type Page } from "@playwright/test";

function result(splitter = "section", count = 3) {
  return {
    schema_version: "lumberjack.chunk.v1",
    document: "Test document",
    metadata: {},
    reference_definitions: {},
    chunk_count: count,
    chunks: Array.from({ length: count }, (_, index) => ({
      chunk_id: splitter + index,
      chunk_type: index === 2 ? "table" : "paragraph",
      body: "Chunk content " + index,
      token_count: index === 2 ? 1400 : 300,
      estimated_token_count: 300,
      headings_token_count: 20,
      body_token_count: index === 2 ? 1380 : 280,
      ancestor_headings: [[1, "Test document"]],
      own_heading: [2, "Section " + index],
      section_level: 2,
      document_title: "Test document",
      document_path: null,
      start_line: index + 1,
      end_line: index + 3,
      source_locations: [],
      protected: index === 2,
    })),
  };
}
async function mockApi(page: Page) {
  await page.route("**/lumber/api/health", (route) =>
    route.fulfill({ json: { status: "ok", version: "0.6.0-test" } }),
  );
  await page.route("**/lumber/api/version", (route) =>
    route.fulfill({ json: { version: "0.6.0-test", commit: null } }),
  );
  await page.route("**/lumber/api/split/**", async (route) => {
    const request = route.request();
    const body = request.headers()["content-type"]?.includes("json")
      ? request.postDataJSON()
      : null;
    await route.fulfill({
      json: result(
        body?.splitter ?? "section",
        body?.splitter === "sibling" ? 2 : 3,
      ),
    });
  });
}
test.describe("mocked workflow", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
  });
  test("input, preview, selection, stale state and export downloads", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    await expect(
      page.getByRole("tab", { name: "分割预览", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await page
      .locator('[class*="segments"]')
      .getByRole("button", { name: "选中分块 #3", exact: true })
      .click();
    await expect(
      page.locator('[class*="inspectorCard"]').first(),
    ).toContainText("#03");
    await expect(
      page.locator('[class*="inspectorCard"]').first(),
    ).toContainText("1400 / 1200");
    await page.getByRole("button", { name: "原文行范围", exact: true }).click();
    await expect(
      page.getByText("行范围仅表示来源关联；同一原文行可能对应多个分块。"),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "调整参数", exact: true })
      .first()
      .click();
    await page.locator('dialog input[type="number"]').first().fill("500");
    await page.getByRole("button", { name: "完成", exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "输入或参数已改变" }),
    ).toBeVisible();
    await expect(
      page.locator('[class*="inspectorCard"]').first(),
    ).toContainText("1400 / 1200");
    await page.getByRole("link", { name: "导出中心", exact: true }).click();
    await page.getByRole("tab", { name: "cURL", exact: true }).click();
    await expect(page.getByRole("tabpanel")).toContainText('"max_tokens":500');
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载 lumber.json" }).click();
    expect((await download).suggestedFilename()).toBe("lumber.json");
  });
  test("A/B comparison, adoption, three plans and partial errors", async ({
    page,
  }) => {
    await page.getByRole("link", { name: "配置对比", exact: true }).click();
    await page.getByRole("button", { name: "运行对比", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "采用方案 B" }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "采用方案 B" }).click();
    await expect(page).toHaveURL(/#split$/);
    await expect(page.locator('aside[class*="inspector"]')).toContainText(
      "sibling",
    );
    await page.getByRole("link", { name: "配置对比", exact: true }).click();
    await page
      .getByRole("button", { name: "调整方案", exact: true })
      .first()
      .click();
    await page.getByLabel("预设", { exact: true }).selectOption("topology");
    await page.getByRole("button", { name: "完成", exact: true }).click();
    await page.route("**/lumber/api/split/text", async (route) => {
      const body = route.request().postDataJSON();
      if (body.splitter === "incremental-sibling")
        await route.fulfill({
          status: 429,
          json: { detail: "rate limit test" },
        });
      else await route.fulfill({ json: result(body.splitter) });
    });
    await page.getByRole("button", { name: "运行对比", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "采用方案 C" }),
    ).toBeEnabled();
    await expect(page.getByRole("alert")).toContainText("HTTP 429");
    await expect(
      page.getByRole("button", { name: "采用方案 A" }),
    ).toBeEnabled();
  });
  test("binary upload forwards format without decoding", async ({ page }) => {
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "document.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-binary"),
      });
    await expect(page.getByText("文件已准备好", { exact: true })).toBeVisible();
    await page.getByLabel("输入格式", { exact: true }).selectOption("pdf");
    const request = page.waitForRequest("**/lumber/api/split/file");
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    expect((await request).postData()).toContain(
      'name="input_format"\r\n\r\npdf',
    );
    await expect(
      page.getByRole("button", { name: "原文行范围", exact: true }),
    ).toHaveCount(0);
  });
  test("input edits cancel a stale response", async ({ page }) => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/lumber/api/split/text", async (route) => {
      await gate;
      await route.fulfill({ json: result() }).catch(() => {});
    });
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "取消请求", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "文档输入", exact: true })
      .fill("new source");
    release();
    await expect(
      page.getByRole("tab", { name: "分割预览", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "运行分割", exact: true }),
    ).toBeEnabled();
  });
  test("a slow file read cannot replace later pasted input", async ({
    page,
  }) => {
    await page.evaluate(() => {
      const read = File.prototype.arrayBuffer;
      File.prototype.arrayBuffer = async function () {
        await new Promise((resolve) => setTimeout(resolve, 400));
        return read.call(this);
      };
    });
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "slow.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("# Old file"),
      });
    await expect(
      page.getByRole("button", { name: "运行分割", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "清除", exact: true }).click();
    await page
      .getByRole("textbox", { name: "文档输入", exact: true })
      .fill("# New pasted input");
    await page.waitForTimeout(500);
    await expect(
      page.getByRole("textbox", { name: "文档输入", exact: true }),
    ).toHaveValue("# New pasted input");
    const request = page.waitForRequest("**/lumber/api/split/text");
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    expect((await request).postDataJSON().text).toBe("# New pasted input");
  });
  test("HTTP errors preserve their status and allow retry", async ({
    page,
  }) => {
    for (const status of [413, 422, 503]) {
      await page.route("**/lumber/api/split/text", (route) =>
        route.fulfill({ status, json: { detail: "request failed" } }),
      );
      await page.getByRole("button", { name: "运行分割", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText("HTTP " + status);
      await expect(
        page.getByRole("button", { name: "运行分割", exact: true }),
      ).toBeEnabled();
    }
  });
  test("dialogs restore focus, themes and language persist, phone navigation works", async ({
    page,
  }) => {
    const adjust = page.getByRole("button", { name: "调整参数", exact: true });
    await adjust.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(adjust).toBeFocused();
    await page.getByRole("button", { name: "切换浅色主题" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Run split", exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page
      .getByRole("link", { name: "Export center", exact: true })
      .click();
    await expect(page.getByRole("tab", { name: "Python" })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
  test("map selects chunks beyond initial render and screenshots every page/theme", async ({
    page,
  }) => {
    await page.route("**/lumber/api/split/text", (route) =>
      route.fulfill({ json: result("section", 65) }),
    );
    await page.getByRole("button", { name: "运行分割", exact: true }).click();
    await page
      .locator('[class*="segments"]')
      .getByRole("button", { name: "选中分块 #65", exact: true })
      .click();
    await expect(page.locator('[data-chunk-index="64"]')).toBeVisible();
    for (const theme of ["dark", "light"]) {
      if (theme === "light")
        await page.getByRole("button", { name: "切换浅色主题" }).click();
      for (const route of ["split", "compare", "export"]) {
        await page
          .getByRole("link", {
            name:
              route === "split"
                ? "分割预览"
                : route === "compare"
                  ? "配置对比"
                  : "导出中心",
            exact: true,
          })
          .click();
        if (route === "compare") {
          await page
            .getByRole("button", { name: "运行对比", exact: true })
            .click();
          await expect(
            page.getByRole("button", { name: "采用方案 B" }),
          ).toBeEnabled();
        }
        await page.screenshot({
          path: "test-results/" + route + "-" + theme + ".png",
        });
        for (const viewport of [
          { width: 1280, height: 800 },
          { width: 390, height: 844 },
        ]) {
          await page.setViewportSize(viewport);
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
          ).toBe(true);
          await page.screenshot({
            path:
              "test-results/" +
              route +
              "-" +
              theme +
              "-" +
              viewport.width +
              ".png",
          });
        }
        await page.setViewportSize({ width: 1600, height: 1000 });
      }
    }
  });
});
