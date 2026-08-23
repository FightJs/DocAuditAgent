import { expect, test } from "vitest";

test("test environment is available", () => {
  expect(import.meta.env.MODE).toBe("test");
});
