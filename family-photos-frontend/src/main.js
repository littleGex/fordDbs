import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import './style.css'; // If using Tailwind or standard CSS

const app = createApp(App);
app.use(createPinia());
app.mount('#app');
