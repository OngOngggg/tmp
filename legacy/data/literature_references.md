# 可追溯的设计参考

这些文献用于提供设计原则，不把它们当作本项目效果的直接证据。

1. Horvitz, E. (1999). *Principles of Mixed-Initiative User Interfaces*. Proceedings of CHI 1999. 关键启示：系统主动性要和用户当前任务、注意力及中断成本协调。
2. Iqbal, S. T., & Bailey, B. P. (2008). *Effects of Intelligent Notification Management on Users and Their Tasks*. Proceedings of CHI 2008. 关键启示：通知管理需要考虑任务阶段和中断时机，减少不必要打扰。
3. VanLehn, K. (2006). *The Behavior of Tutoring Systems*. International Journal of Artificial Intelligence in Education, 16, 227–265. 关键启示：辅导系统应根据学生状态逐步提供帮助，而不是直接给出高强度干预。
4. Roll, I., Aleven, V., McLaren, B. M., & Koedinger, K. R. (2011). *Improving Students' Help-Seeking Skills Using Metacognitive Feedback in an Intelligent Tutoring System*. Learning and Instruction, 21(2), 267–280. 关键启示：帮助寻求应保留学生选择权，并把“是否需要帮助”与“帮助后的行为”分开评估。
5. Wood, D., Bruner, J. S., & Ross, G. (1976). *The Role of Tutoring in Problem Solving*. Journal of Child Psychology and Psychiatry, 17(2), 89–100. 关键启示：支架式帮助应逐步、可撤销，并根据学习者当前需要调整强度。

## 如何使用这些参考

- 它们支持“注意力感知、低打扰、渐进式帮助、用户可撤销”的设计方向。
- 它们不支持直接把 `idle`、按键数或本项目的离线 Precision 当作学生真实卡顿的充分证据。
- 本项目仍需通过 shadow mode 和小规模 A/B 获得真实行为证据。

