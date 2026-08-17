/** O8 用户端考试工坊模型。 */

/** 试卷概要（我的试卷 / 收藏副本） */
export interface WorkshopPaperBrief {
  id: number
  name: string
  total_score: number
  pass_score: number
  duration: number
  question_count: number
  gen_mode: string
  status: string
  source_paper_id: number | null
  is_copy: boolean
  create_time: string | null
}

/** 我的试卷列表行 */
export type UserPaperItem = WorkshopPaperBrief

/** 分享给我的试卷行 */
export interface SharedPaperItem extends WorkshopPaperBrief {
  publisher_name: string
  share_time: string | null
}
