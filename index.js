// 简单的前端入口文件

// 确保在 GitHub Pages 上能正确处理路由
if (typeof window !== 'undefined') {
    // 检测主题偏好并应用
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.classList.add('dark');
    }
    
    // 主题切换功能
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const applyTheme = function() {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        };
        let themeRippleRunning = false;
        themeToggle.addEventListener('click', function(event) {
            const canRipple = typeof document.startViewTransition === 'function'
                && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
                && !document.hidden;

            if (!canRipple || themeRippleRunning) {
                applyTheme();
                return;
            }

            const rect = themeToggle.getBoundingClientRect();
            const originX = event.clientX || (rect.left + rect.width / 2);
            const originY = event.clientY || (rect.top + rect.height / 2);
            document.documentElement.style.setProperty('--ripple-x', originX + 'px');
            document.documentElement.style.setProperty('--ripple-y', originY + 'px');

            themeRippleRunning = true;
            let transition;
            try {
                transition = document.startViewTransition(applyTheme);
            } catch (e) {
                themeRippleRunning = false;
                applyTheme();
                return;
            }
            const unlock = function() { themeRippleRunning = false; };
            transition.ready.catch(function() {});
            transition.finished.then(unlock, unlock);
        });
    }
}

// 导出一个简单的函数以便在其他地方使用
export function initPage() {
    console.log('个人主页已初始化');
}