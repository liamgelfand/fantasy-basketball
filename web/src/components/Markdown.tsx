import { Typography } from '@mantine/core'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import classes from './Markdown.module.css'

export function Markdown({ children }: { children: string }) {
  return (
    <Typography className={classes.root}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </Typography>
  )
}
