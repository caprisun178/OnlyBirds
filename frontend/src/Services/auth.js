// Services/auth.js — stands in for real sign-in until auth exists
// (user-profiles.md's auth section is still "Planned"). Any screen that
// needs "the current user" should call getCurrentUserId() from here rather
// than importing testProfile directly, so swapping in real auth later only
// means changing this one file .

import { getCurrentUser } from '../testData/testProfile.js';

export function getCurrentUserId() {
  return getCurrentUser().id;
}