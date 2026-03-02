import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import ProfilePicker from '../components/ProfilePicker.vue';
import UserProfile from '../views/UserProfile.vue';

const routes = [
  {
    path: '/',
    name: 'login',
    component: ProfilePicker
  },
  {
    path: '/home',
    name: 'home',
    component: UserProfile,
    meta: { requiresAuth: true } // Mark this as a protected route
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// GLOBAL NAVIGATION GUARD
router.beforeEach((to, from, next) => {
  const auth = useAuthStore();

  // If the route requires auth and user isn't logged in, send to login
  if (to.meta.requiresAuth && !auth.currentUser) {
    next({ name: 'login' });
  }
  // If user is already logged in and tries to go to login page, send to home
  else if (to.name === 'login' && auth.currentUser) {
    next({ name: 'home' });
  }
  else {
    next();
  }
});

export default router;
