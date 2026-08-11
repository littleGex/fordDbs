// src/utils/avatar.js
// Always returns a displayable avatar URL — the user's uploaded photo,
// or an auto-generated initials icon as a fallback.
export const getAvatar = (user) => {
  if (user?.profile_photo_url) return user.profile_photo_url;
  const safeName = encodeURIComponent(user?.display_name || 'User');
  return `https://ui-avatars.com/api/?name=${safeName}&background=333333&color=fff&size=150`;
};
