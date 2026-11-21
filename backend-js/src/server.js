import cors from 'cors';
import express from 'express';
import { config } from './config.js';
import { migrate } from './db.js';
import { aiContentRouter } from './routes/aiContent.js';
import { authRouter } from './routes/auth.js';
import { businessRouter } from './routes/business.js';

migrate();

const app = express();
app.use(cors());
app.use(express.json());

app.use('/auth', authRouter);
app.use('/businesses', businessRouter);
app.use('/', aiContentRouter);

app.get('/health', (req, res) => res.json({ status: 'ok' }));

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ detail: 'Internal server error' });
});

app.listen(config.port, '0.0.0.0', () => {
  console.log(`MarketUp backend (Node) listening on 0.0.0.0:${config.port}`);
});
