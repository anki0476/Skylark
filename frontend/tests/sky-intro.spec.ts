import {test, expect} from '@playwright/test';

test('SKY introduces Skylark on the first landing visit only', async ({page}) => {
  await page.goto('/#');
  const intro = page.getByRole('dialog', {name: 'Meet SKY'});
  await expect(intro).toBeVisible();
  await expect(intro.getByRole('heading', {name: 'Hi, I’m SKY!'})).toBeVisible({timeout: 10000});
  await page.screenshot({path: '../.cache/skylark-sky-intro.png'});
  await intro.getByRole('button', {name: 'Let’s explore'}).click();
  await expect(intro).toHaveCount(0);
  await page.reload();
  await expect(intro).toHaveCount(0);
});

test('SKY shows the welcome message immediately with reduced motion', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await page.goto('/#');
  const intro = page.getByRole('dialog', {name: 'Meet SKY'});
  await expect(intro.getByRole('heading', {name: 'Hi, I’m SKY!'})).toBeVisible();
  await intro.getByRole('button', {name: 'Skip intro'}).click();
  await expect(intro).toHaveCount(0);
});
