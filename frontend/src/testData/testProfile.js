// Stand-in for the real signed-in user until user-profiles.md ships (auth +
// `GET /users/{username}` are both "Planned"). Any screen that needs "the
// current user" imports `testProfile` instead of a real auth/profile call.
//
// Swap this for `Dao/user.js` + `Services/auth.js` once those exist — nothing
// that consumes `getCurrentUser()` should need to change shape, since this
// mirrors the profile fields documented in docs/features/user-profiles.md.

export const testProfile = {
  id: 'u1',
  username: 'test-birder',
  avatar_url: null,
  default_region: 'US-NC',
};

export function getCurrentUser() {
  return testProfile;
}
