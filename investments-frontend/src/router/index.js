import {createRouter, createWebHistory} from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import AdminView from '../views/AdminView.vue'
import LoginView from '../views/LoginView.vue'
import {isLoggedIn} from '../auth'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {path: '/login', component: LoginView, meta: {public: true}},
        {path: '/', component: DashboardView},
        {path: '/admin', component: AdminView}
    ]
})

// This is the "Bouncer" that checks every page change: the whole app
// is for logged-in parents
router.beforeEach((to) => {
    if (to.meta.public) {
        return isLoggedIn.value ? '/' : true
    }
    return isLoggedIn.value ? true : '/login'
})

export default router
