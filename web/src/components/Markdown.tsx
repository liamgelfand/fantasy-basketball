import { Typography } from '@mantine/core'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ComponentProps } from 'react'
import classes from './Markdown.module.css'

// Claude cites news sources: open them in a new tab so the conversation stays put.
function ExternalLink({ node: _node, ...props }: ComponentProps<'a'> & { node?: unknown }) {
  return <a {...props} target="_blank" rel="noopener noreferrer" />
}

export function Markdown({ children }: { children: string }) {
  return (
    <Typography className={classes.root}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ExternalLink }}>
        {children}
      </ReactMarkdown>
    </Typography>
  )
}
