import {createRouter, createWebHistory} from 'vue-router'
import HomeView from '../views/HomeView.vue'
import AdminView from '../views/AdminView.vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE;

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {path: '/', component: HomeView},
        {
            path: '/admin',
            component: AdminView,
            meta: {requiresAuth: true} // Mark this route as protected
        }
    ]
})

// This is the "Bouncer" that checks every page change
router.beforeEach(async (to, from, next) => {
    if (to.meta.requiresAuth) {
        let password = localStorage.getItem('admin_token');

        if (!password) {
            password = prompt("Enter Admin Password:");
        }

        try {
            await axios.post(`${API_BASE}/verify-admin`, null, {
                params: {password: password} // This sends it as ?password=...
            });
            localStorage.setItem('admin_token', password);
            next();
        } catch (error) {
            alert("Wrong password!");
            localStorage.removeItem('admin_token');
            next('/');
        }
    } else {
        next();
    }
})

export default router
