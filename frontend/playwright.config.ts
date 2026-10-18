import { defineConfig } from '@playwright/test';
const port=process.env.SKYLARK_TEST_PORT||'8000';
export default defineConfig({testDir:'./tests',timeout:90000,workers:1,
 webServer:process.env.SKYLARK_TEST_SERVER==='1'?{command:`python -m skylark --data .cache/browser-tests serve --port ${port}`,cwd:'..',url:`http://127.0.0.1:${port}/api/v1/status`,reuseExistingServer:false,timeout:60000,env:{SKYLARK_LIVE_ENABLED:'0'}}:undefined,
 use:{baseURL:`http://127.0.0.1:${port}`,headless:true,channel:process.env.CI?'chromium':'msedge',trace:'retain-on-failure'},reporter:'list'});
