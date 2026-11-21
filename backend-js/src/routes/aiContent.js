import { Router } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { db } from '../db.js';
import { requireAuth } from '../middleware/auth.js';
import { contentGenerationService } from '../services/contentGenerationService.js';

export const aiContentRouter = Router();

function serializePost(row) {
  return {
    id: row.id,
    business_id: row.business_id,
    occasion: row.occasion,
    caption: row.caption,
    hashtags: JSON.parse(row.hashtags || '[]'),
    cta: row.cta,
    image_prompt: row.image_prompt,
    generated_image: row.generated_image,
    reel_idea: row.reel_idea,
    carousel_slides: JSON.parse(row.carousel_slides || '[]'),
    status: row.status,
    ai_model_used: row.ai_model_used,
    created_at: row.created_at,
  };
}

function getBusinessOr404(req, res) {
  const business = db
    .prepare('SELECT * FROM businesses WHERE user_id = ?')
    .get(req.user.id);
  if (!business) {
    res.status(404).json({ detail: 'Complete business onboarding first' });
    return null;
  }
  return business;
}

aiContentRouter.post('/ai/generate', async (req, res) => {
  const body = req.body || {};
  const business = body.business_profile;
  if (!business?.id || !business.business_name || !business.sector) {
    return res.status(422).json({ detail: 'A complete business_profile is required' });
  }

  const options = {
    occasion: body.occasion,
    postType: body.post_type,
    tone: body.tone,
    goal: body.goal,
    includeHashtags: body.include_hashtags !== false,
    includeCta: body.include_cta !== false,
    includeImagePrompt: body.include_image_prompt !== false,
    includeReelIdea: body.include_reel_idea === true,
  };
  const occasion = options.occasion || null;

  let result;
  try {
    result = await contentGenerationService.generatePostContent(
      business,
      options,
      req.get('X-Api-Key'),
    );
  } catch (err) {
    if (err.message === 'AI_NOT_CONFIGURED') {
      return res.status(503).json({ detail: 'AI generation not configured' });
    }
    return res.status(502).json({ detail: `Content generation failed: ${err.message}` });
  }

  return res.status(201).json({
    id: uuidv4(),
    business_id: business.id,
    occasion,
    caption: result.caption,
    hashtags: result.hashtags || [],
    cta: result.cta || '',
    image_prompt: result.image_prompt || '',
    generated_image: result.generated_image || null,
    reel_idea: result.reel_idea || null,
    carousel_slides: result.carousel_slides || [],
    status: 'pending',
    ai_model_used: result.model_used,
    created_at: new Date().toISOString(),
  });
});

aiContentRouter.get('/businesses/me/posts', requireAuth, (req, res) => {
  const business = getBusinessOr404(req, res);
  if (!business) return;

  const statusFilter = req.query.status_filter;
  const rows = statusFilter
    ? db
        .prepare(
          'SELECT * FROM posts WHERE business_id = ? AND status = ? ORDER BY created_at DESC',
        )
        .all(business.id, statusFilter)
    : db
        .prepare('SELECT * FROM posts WHERE business_id = ? ORDER BY created_at DESC')
        .all(business.id);

  return res.json(rows.map(serializePost));
});

aiContentRouter.post('/posts/:id/approve', requireAuth, (req, res) => {
  const business = getBusinessOr404(req, res);
  if (!business) return;

  const post = db
    .prepare('SELECT * FROM posts WHERE id = ? AND business_id = ?')
    .get(req.params.id, business.id);
  if (!post) return res.status(404).json({ detail: 'Post not found' });

  db.prepare(
    "UPDATE posts SET status = 'scheduled', approved_at = datetime('now') WHERE id = ?",
  ).run(post.id);

  return res.json({ id: post.id, status: 'scheduled' });
});

aiContentRouter.post('/posts/:id/reject', requireAuth, (req, res) => {
  const business = getBusinessOr404(req, res);
  if (!business) return;

  const post = db
    .prepare('SELECT * FROM posts WHERE id = ? AND business_id = ?')
    .get(req.params.id, business.id);
  if (!post) return res.status(404).json({ detail: 'Post not found' });

  db.prepare("UPDATE posts SET status = 'rejected' WHERE id = ?").run(post.id);

  return res.json({ id: post.id, status: 'rejected' });
});
