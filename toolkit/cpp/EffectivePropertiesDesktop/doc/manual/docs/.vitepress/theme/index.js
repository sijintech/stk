import DefaultTheme from 'vitepress/theme'
import MyLayout from './MyLayout.vue'
import "./custom.css"
import Mermaid from "./Mermaid.vue";

export default {
  ...DefaultTheme,
  enhanceApp({ app }) {
    // register global components
    // app    .component('Mermaid',Mermaid /* ... */)
    app.component('Mermaid', Mermaid);
  },
  Layout: MyLayout
}