import assert from "node:assert/strict";
import { test } from "node:test";
import { confirmDatabaseReset } from "../src/databaseResetConfirmation.ts";

for (const answers of [[false], [true, false], [true, true]]) {
  test(`database reset confirmations: ${answers}`, () => {
    const pending = [...answers];
    const messages = [];
    const accepted = confirmDatabaseReset(message => {
      messages.push(message);
      return pending.shift();
    });
    assert.equal(accepted, answers.length === 2 && answers.every(Boolean));
    assert.equal(messages.length, answers.length);
    assert.equal(pending.length, 0);
  });
}
