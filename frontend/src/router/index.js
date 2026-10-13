import {createRouter, createWebHistory} from 'vue-router'
import HomeView from '../views/HomeView.vue'
import AdminView from '../views/AdminView.vue'
import LoginView from '../views/LoginView.vue'
import {isLoggedIn, isParent} from '../auth'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {path: '/login', component: LoginView, meta: {public: true}},
        {path: '/', component: HomeView},
        {
            path: '/admin',
            component: AdminView,
            meta: {requiresParent: true} // Only parents may open this page
        }
    ]
})

// This is the "Bouncer" that checks every page change
router.beforeEach((to) => {
    if (to.meta.public) {
        return isLoggedIn.value ? '/' : true
    }
    if (!isLoggedIn.value) {
        return '/login'
    }
    if (to.meta.requiresParent && !isParent.value) {
        return '/'
    }
    return true
})

export default router
