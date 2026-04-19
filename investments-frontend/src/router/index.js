import {createRouter, createWebHistory} from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import AdminView from '../views/AdminView.vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8005/v1';

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {path: '/', component: DashboardView},
        {
            path: '/admin',
            component: AdminView,
            meta: {requiresAuth: true}
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
            await axios.post(`${API_BASE}/pocket-money/verify-admin`, null, {
                params: {password: password}
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
